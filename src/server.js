'use strict';

const net = require('node:net');
const { randomBytes, createHash } = require('node:crypto');
const path = require('node:path');

async function connect(socketPath) {
  const socket = net.createConnection(socketPath);
  const key = randomBytes(16).toString('base64');
  let buffer = Buffer.alloc(0), ready = false, fragment = [], fragmentBytes = 0;
  let receive = () => {}, failed = () => {};
  function send(data, opcode = 1) {
    const body = Buffer.from(data); const mask = randomBytes(4);
    const header = Buffer.alloc(body.length < 126 ? 2 : 4);
    header[0] = 0x80 | opcode; header[1] = 0x80 | (body.length < 126 ? body.length : 126);
    if (body.length >= 126) header.writeUInt16BE(body.length, 2);
    const masked = Buffer.from(body); for (let i = 0; i < masked.length; i++) masked[i] ^= mask[i % 4];
    socket.write(Buffer.concat([header, mask, masked]));
  }
  const handshake = new Promise((resolve, reject) => {
    socket.on('error', error => { reject(error); failed(error); });
    socket.on('close', () => { const error = new Error('metadata_connection_closed'); reject(error); failed(error); });
    socket.on('connect', () => socket.write(`GET / HTTP/1.1\r\nHost: localhost\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: ${key}\r\nSec-WebSocket-Version: 13\r\n\r\n`));
    socket.on('data', chunk => {
      try {
        buffer = Buffer.concat([buffer, chunk]);
        if (buffer.length > 4 * 1024 * 1024) throw new Error('metadata_too_large');
        if (!ready) {
          const end = buffer.indexOf('\r\n\r\n'); if (end < 0) return;
          const headers = buffer.subarray(0, end).toString('ascii');
          const accept = createHash('sha1').update(key + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11').digest('base64');
          if (!/^HTTP\/1\.1 101\b/.test(headers) || !headers.includes(accept)) throw new Error('metadata_handshake_failed');
          buffer = buffer.subarray(end + 4); ready = true; resolve();
        }
        while (buffer.length >= 2) {
          const opcode = buffer[0] & 15, fin = !!(buffer[0] & 128);
          let size = buffer[1] & 127, offset = 2;
          if (buffer[1] & 128) throw new Error('metadata_invalid_frame');
          if (size === 126) { if (buffer.length < 4) return; size = buffer.readUInt16BE(2); offset = 4; }
          if (size === 127) { if (buffer.length < 10) return; const n = buffer.readBigUInt64BE(2); if (n > 2097152n) throw new Error('metadata_too_large'); size = Number(n); offset = 10; }
          if (size > 2097152) throw new Error('metadata_too_large');
          if (buffer.length < offset + size) return;
          const body = buffer.subarray(offset, offset + size); buffer = buffer.subarray(offset + size);
          if (opcode === 8) { socket.end(); return; }
          if (opcode === 9) { send(body, 10); continue; }
          if (opcode === 10) continue;
          if (opcode !== 0 && opcode !== 1) throw new Error('metadata_invalid_frame');
          fragment.push(body); fragmentBytes += body.length;
          if (fragmentBytes > 2097152) throw new Error('metadata_too_large');
          if (fin) { const message = Buffer.concat(fragment).toString('utf8'); fragment = []; fragmentBytes = 0; receive(message); }
        }
      } catch (error) { reject(error); failed(error); socket.destroy(); }
    });
  });
  const timeout = setTimeout(() => socket.destroy(new Error('metadata_timeout')), 2500);
  try { await handshake; } finally { clearTimeout(timeout); }
  return { send, onMessage: callback => { receive = callback; }, onError: callback => { failed = callback; }, close: () => socket.destroy() };
}
async function targetIdentity(home, execution, threadId) {
  const command = execution?.commandLine?.value || '';
  const remote = command.match(/--remote(?:=|\s+)["']?([^\s"']+)/);
  if (remote && !remote[1].startsWith('unix://')) throw new Error('remote_server_not_supported');
  const socketPath = remote && remote[1] !== 'unix://'
    ? remote[1].slice(7) : path.join(home, 'app-server-control', 'app-server-control.sock');
  const socket = await connect(socketPath);
  let nextId = 0; const pending = new Map();
  const deadline = Date.now() + 4000;
  function fail(error) { for (const item of pending.values()) item.reject(error); pending.clear(); }
  const timer = setTimeout(() => { fail(new Error('metadata_timeout')); socket.close(); }, 4000);
  socket.onError(fail);
  socket.onMessage(line => {
    try {
      const message = JSON.parse(line); const item = pending.get(message.id);
      if (!item) return;
      pending.delete(message.id);
      if (message.error) item.reject(new Error('metadata_' + message.error.code));
      else item.resolve(message.result);
    } catch (error) { fail(error); }
  });
  function request(method, params) {
    if (Date.now() >= deadline) return Promise.reject(new Error('metadata_timeout'));
    return new Promise((resolve, reject) => {
      const id = ++nextId; pending.set(id, { resolve, reject });
      socket.send(JSON.stringify({ jsonrpc: '2.0', id, method, params }));
    });
  }
  try {
    await request('initialize', { clientInfo: { name: 'codex-focus-notifications', version: '0.2.0' },
      capabilities: { experimentalApi: true } });
    socket.send(JSON.stringify({ jsonrpc: '2.0', method: 'initialized' }));
    const all = new Map(); let cursor;
    for (let page = 0; page < 20; page++) {
      const result = await request('thread/list', { limit: 100, ...(cursor ? { cursor } : {}) });
      for (const thread of result.data || []) all.set(thread.id, thread);
      cursor = result.nextCursor;
      if (!cursor) break;
    }
    if (cursor) throw new Error('metadata_incomplete');
    const loaded = await request('thread/loaded/list', {});
    const extra = (loaded.data || []).filter(id => !all.has(id));
    if (extra.length > 50) throw new Error('metadata_incomplete');
    for (const id of extra) {
      const result = await request('thread/read', { threadId: id, includeTurns: false });
      all.set(id, result.thread);
    }
    const target = all.get(threadId);
    if (!target || typeof target.name !== 'string' || !target.name.trim()) throw new Error('unique_name_required');
    if (target.name.length > 200 || /[\x00-\x1f\x7f-\x9f]/.test(target.name)) throw new Error('unsupported_session_name');
    if (target.status?.type === 'active') throw new Error('target_task_busy');
    const query = target.name.toLowerCase();
    const matches = [...all.values()].filter(thread =>
      `${thread.name || ''} ${thread.preview || ''} ${thread.cwd || ''}`.toLowerCase().includes(query));
    if (matches.length !== 1 || matches[0].id !== threadId) throw new Error('ambiguous_session_name');
    return { id: threadId, name: target.name, cwd: target.cwd };
  } finally { clearTimeout(timer); socket.close(); }
}

module.exports = { targetIdentity };
