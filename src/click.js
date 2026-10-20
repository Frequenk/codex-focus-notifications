'use strict';

const fs = require('node:fs');
const path = require('node:path');
const { randomUUID } = require('node:crypto');
const { execFile } = require('node:child_process');
const { jump } = require('./jump');
const { Screen } = require('./screen');
const { targetIdentity } = require('./server');
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;

function writeJson(file, value) {
  fs.mkdirSync(path.dirname(file), { recursive: true, mode: 0o700 });
  const temp = file + '.tmp';
  fs.writeFileSync(temp, JSON.stringify(value) + '\n', { mode: 0o600 });
  fs.renameSync(temp, file);
}

class ClickBridge {
  constructor(options) {
    this.options = options; this.records = new Map(); this.busy = false;
    this.disposed = false; this.stage = 'idle'; this.lastPublish = 0;
    if (options.debug) this.debugScreens = new Map();
  }
  reset(home) {
    this.removeRegistry(); this.home = home; this.records.clear();
    this.registry = path.join(home, 'vscode-click', 'windows', this.options.windowId + '.json');
    this.requests = path.join(home, 'vscode-click', 'requests', this.options.windowId);
    fs.mkdirSync(this.requests, { recursive: true, mode: 0o700 });
    this.lastPublish = 0;
  }
  record(terminal) {
    let record = this.records.get(terminal);
    if (!record) {
      record = { terminal, id: randomUUID(), generation: 0, live: true, prefix: null,
        currentId: null, seen: new Map(), seenAt: 0, execution: null };
      this.records.set(terminal, record);
    }
    return record;
  }
  startCommand(terminal, execution) {
    const record = this.record(terminal);
    if (record.live && record.execution) this.retire(record);
    record.generation++; record.live = true; record.prefix = null; record.currentId = null;
    record.seen.clear(); record.execution = execution; record.resolving = false; record.lastResolve = 0;
  }
  endCommand(terminal, execution) {
    const record = this.records.get(terminal);
    if (!record || !record.live || record.execution !== execution) return;
    this.retire(record);
  }
  closeTerminal(terminal) {
    const record = this.records.get(terminal);
    if (record && record.live) this.retire(record);
    this.records.delete(terminal);
    this.debugScreens?.delete(terminal);
  }
  retire(record) {
    // 先保存历史，再撤销映射；重复的退出事件不会再次清理。
    const ids = [...record.seen.keys()];
    const unresolved = record.prefix && !record.currentId ? record.prefix : null;
    record.generation++; record.live = false; record.currentId = null; record.prefix = null;
    record.seen.clear(); record.execution = null;
    this.publish();
    const finish = extra => {
      if (this.disposed) return;
      const all = [...new Set([...ids, ...(extra ? [extra] : [])])];
      const remaining = all.filter(id => ![...this.records.values()].some(other => other.live && other.seen.has(id)));
      if (remaining.length) this.options.closed(remaining);
    };
    if (unresolved) this.options.resolve(unresolved).then(finish).catch(() => finish());
    else finish();
  }
  title(terminal, prefix) {
    const record = this.record(terminal);
    if (!record.live) return;
    if (record.prefix === prefix) {
      if (record.currentId || record.resolving || Date.now() - record.lastResolve < 3000) return;
    } else {
      record.prefix = prefix; record.currentId = null; record.seenAt = Date.now();
    }
    if (!prefix) return;
    const generation = record.generation;
    record.resolving = true; record.lastResolve = Date.now();
    this.options.resolve(prefix).then(id => {
      if (this.disposed || !record.live || record.generation !== generation || !id || !UUID.test(id)) return;
      record.seen.set(id, Date.now());
      if (record.prefix === prefix) record.currentId = id;
      this.lastPublish = 0;
    }).catch(() => {}).finally(() => { if (record.generation === generation) record.resolving = false; });
  }
  feed(terminal, data) {
    if (this.captureTerminal === terminal && this.screen) this.screen.feed(data);
    if (this.debugScreens) {
      if (!this.debugScreens.has(terminal)) this.debugScreens.set(terminal, new Screen());
      this.debugScreens.get(terminal).feed(data);
    }
  }
  debugScreen() { return this.lastDebugScreen || this.debugScreens?.get(this.options.vscode.window.activeTerminal)?.text(); }
  removeRegistry() {
    if (this.registry) { try { fs.unlinkSync(this.registry); } catch {} }
  }
  publish() {
    if (!this.registry || this.disposed) return;
    const terminals = [];
    for (const [terminal, record] of this.records) {
      if (terminal.exitStatus !== undefined && record.live) continue;
      if (record.live && (record.seen.size || record.prefix)) terminals.push({ terminal_id: record.id,
        current_thread_id: record.currentId, thread_prefix: record.prefix,
        thread_ids: [...record.seen.keys()], seen_at_ms: record.seenAt });
    }
    writeJson(this.registry, { version: 1, window_id: this.options.windowId, pid: process.pid,
      updated_at_ms: Date.now(), terminals });
    this.lastPublish = Date.now();
  }
  suppressFocus() {
    if (this.busy) return true;
    if (!this.hold) return false;
    if (!this.options.vscode.window.state.focused || this.options.vscode.window.activeTerminal !== this.hold.terminal
      || this.hold.record.prefix !== this.hold.prefix) { this.hold = null; return false; }
    return true;
  }
  tick() {
    if (this.disposed || !this.home) return;
    try {
      for (const record of this.records.values()) if (record.live && record.prefix && !record.currentId)
        this.title(record.terminal, record.prefix);
      if (Date.now() - this.lastPublish >= 1000) this.publish();
      for (const filename of fs.readdirSync(this.requests).slice(0, 16)) {
        if (!filename.endsWith('.json') || !UUID.test(filename.slice(0, -5))) continue;
        const file = path.join(this.requests, filename); const info = fs.lstatSync(file);
        if (info.isSymbolicLink() || info.uid !== process.getuid() || info.size > 8192) continue;
        const request = JSON.parse(fs.readFileSync(file, 'utf8'));
        fs.unlinkSync(file);
        if (request.version !== 1 || request.window_id !== this.options.windowId
          || request.request_id !== filename.slice(0, -5) || !UUID.test(request.thread_id || '')
          || !UUID.test(request.terminal_id || '') || !(Date.now() - request.created_at_ms >= 0)
          || Date.now() - request.created_at_ms > 30000) continue;
        if (this.busy) { this.result(request, 'ignored_busy'); continue; }
        void this.open(request);
      }
    } catch (error) { this.options.log('Click bridge: ' + (error.code || error.name)); }
  }
  result(request, result, reason) {
    this.lastResult = { result, reason, stage: this.stage, thread_id: request.thread_id };
    if (this.startedAt) this.lastResult.elapsed_ms = Date.now() - this.startedAt;
    if (this.stageTimes) this.lastResult.stages = this.stageTimes;
    writeJson(path.join(this.home, 'vscode-click', 'results', request.request_id + '.json'), {
      version: 1, ...this.lastResult, updated_at_ms: Date.now() });
    this.options.log(`Notification click: ${result}${reason ? ' (' + reason + ')' : ''}`);
  }
  async open(request) {
    const record = [...this.records.values()].find(item => item.id === request.terminal_id
      && item.live && item.terminal.exitStatus === undefined);
    if (!record) { this.result(request, 'failed', 'terminal_unavailable'); return; }
    const generation = record.generation;
    this.hold = null; this.busy = true; this.stage = 'focus'; this.lastDebugScreen = undefined;
    this.startedAt = Date.now(); this.stageTimes = [];
    this.options.changed();
    try {
      if (!record.seen.has(request.thread_id)) {
        if (!record.prefix || await this.options.resolve(record.prefix) !== request.thread_id)
          throw new Error('session_binding_unavailable');
        record.currentId = request.thread_id; record.seen.set(request.thread_id, Date.now());
      }
      await this.options.vscode.commands.executeCommand('workbench.action.focusWindow');
      record.terminal.show(false);
      const focusDeadline = Date.now() + 1500;
      while (Date.now() < focusDeadline && (this.options.vscode.window.activeTerminal !== record.terminal
        || !this.options.vscode.window.state.focused)) await new Promise(resolve => setTimeout(resolve, 25));
      if (this.options.vscode.window.activeTerminal !== record.terminal || !this.options.vscode.window.state.focused)
        throw new Error('window_not_focused');
      if (record.currentId !== request.thread_id) {
        if (!record.execution) throw new Error('restart_tui_required');
        const version = await new Promise((resolve, reject) => {
          execFile(this.options.codex(), ['--version'], { timeout: 1500 },
            (error, stdout) => error ? reject(error) : resolve(stdout.trim()));
        });
        if (version !== 'codex-cli 0.163.0') throw new Error('unsupported_codex_version');
        this.stage = 'metadata';
        const identity = await targetIdentity(this.home, record.execution, request.thread_id);
        this.captureTerminal = record.terminal;
        await jump({ threadId: request.thread_id, identity,
          send: data => record.terminal.sendText(data, false),
          alive: () => !this.disposed && record.live && record.generation === generation && record.terminal.exitStatus === undefined
            && this.options.vscode.window.activeTerminal === record.terminal && this.options.vscode.window.state.focused,
          currentId: () => record.currentId,
          stage: value => { this.stage = value; this.stageTimes.push({ stage: value, at_ms: Date.now() - this.startedAt }); },
          capture: screen => {
            if (!screen && this.options.debug && this.screen) this.lastDebugScreen = this.screen.text();
            this.screen = screen;
          } });
      }
      this.result(request, 'opened');
    } catch (error) {
      this.hold = { terminal: record.terminal, record, prefix: record.prefix };
      this.result(request, 'failed', error.message || error.name);
      void this.options.vscode.window.showInformationMessage(
        '已定位原终端，但未能自动切回目标会话。已停止按键操作，请手动选择该会话。');
    } finally {
      this.screen = null; this.captureTerminal = null; this.busy = false;
      this.stage = 'idle'; this.options.changed();
    }
  }
  status() { return { stage: this.stage, busy: this.busy, terminals: this.records.size, last_result: this.lastResult,
    bindings: [...this.records.values()].map(record => ({ terminal_id: record.id,
      current_thread_id: record.currentId, prefix: record.prefix, live: record.live })) }; }
  dispose() { this.disposed = true; this.removeRegistry(); }
}

module.exports = { ClickBridge };
