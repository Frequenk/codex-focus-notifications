// 隔离运行真实终端桥和 Python 通知桥，系统通知命令使用可记录的替身。
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { execFileSync } = require('node:child_process');
const { ClickBridge } = require('../src/click');
const assert = require('node:assert/strict');
const root = fs.mkdtempSync(path.join(os.tmpdir(), 'codex-exit-smoke-'));
const ids = ['00111111-1111-1111-1111-111111111111','00222222-2222-2222-2222-222222222222','00333333-3333-3333-3333-333333333333','00444444-4444-4444-4444-444444444444'];
const log = path.join(root, 'notifier.log'); const binary = path.join(root, 'notifier');
fs.writeFileSync(binary, '#!/usr/bin/env python3\nimport os,sys,json\nwith open(os.environ["MOCK_LOG"],"a") as f:f.write(json.dumps(sys.argv[1:])+"\\n")\n', { mode: 0o700 });
fs.mkdirSync(path.join(root, 'notification-bridge'));
fs.writeFileSync(path.join(root, 'notification-bridge/runtime.json'), JSON.stringify({ notifier: binary }));
const python = process.env.PYTHON || 'python3';
const deleted = () => fs.existsSync(log) ? fs.readFileSync(log, 'utf8').trim().split('\n').map(s => JSON.parse(s)[1]) : [];
const window1 = 'aaaaaaaa-1111-1111-1111-111111111111'; const window2 = 'bbbbbbbb-2222-2222-2222-222222222222';
function bridge(windowId) {
  const b = new ClickBridge({ windowId, vscode: { window: { state: { focused: false } } }, log: () => {},
    resolve: async prefix => ids.find(id => id.startsWith(prefix)),
    closed: values => execFileSync(python, [path.join(__dirname, '../scripts/notify.py'), '--vscode-clear-closed'],
      { input: JSON.stringify({ thread_ids: values }), env: { ...process.env, CODEX_HOME: root, MOCK_LOG: log } }) });
  b.reset(root); return b;
}
const pause = () => new Promise(r => setTimeout(r, 20));
(async () => {
  const a = bridge(window1), b = bridge(window2);
  const first = {}, sibling = {}, foreign = {}, last = {};
  const command = {};
  a.startCommand(first, command); a.title(first, ids[0]); await pause(); a.title(first, ids[1]); await pause();
  a.startCommand(sibling, {}); a.title(sibling, ids[0]); await pause();
  b.startCommand(foreign, command); b.title(foreign, ids[1]); await pause(); a.publish(); b.publish();
  a.closeTerminal(first); assert.deepEqual(deleted(), [], '共享会话被误删');
  a.closeTerminal(first); a.endCommand(first, command); assert.deepEqual(deleted(), []);
  a.closeTerminal(sibling); assert.deepEqual(deleted(), ['codex-' + ids[0]]);
  b.endCommand(foreign, command); assert.deepEqual(deleted(), ['codex-' + ids[0], 'codex-' + ids[1]]);
  a.startCommand(last, command); a.title(last, ids[2]); await pause(); a.title(last, ids[3]); await pause(); a.publish();
  a.endCommand(last, command); a.closeTerminal(last);
  assert.deepEqual(deleted(), ids.map(id => 'codex-' + id), '历史会话未清理或重复删除');
  a.closeTerminal({}); a.dispose(); b.dispose();
  assert.deepEqual(deleted(), ids.map(id => 'codex-' + id), '扩展停用被当作退出');

  // 走真实点击失败流程，外部窗口操作和提示由本机替身接收。
  const messages = [];
  const vscode = { window: { state: { focused: true }, showInformationMessage: message => messages.push(message) },
    commands: { executeCommand: async () => {} } };
  const target = { show() { vscode.window.activeTerminal = target; } };
  const c = new ClickBridge({ windowId: window1, vscode, changed: () => {}, log: () => {},
    resolve: async prefix => ids.find(id => id.startsWith(prefix)) });
  c.reset(path.join(root, 'click-flow'));
  c.title(target, ids[0]); await pause(); c.title(target, ids[1]); await pause();
  const record = c.records.get(target);
  const NativeDate = Date;
  try {
    global.Date = class extends NativeDate {
      constructor(...args) { super(...(args.length ? args : [2024, 0, 2, 3, 4, 5])); }
    };
    await c.open({ terminal_id: record.id, thread_id: ids[0], request_id: window1 });
  } finally { global.Date = NativeDate; c.dispose(); }
  assert.equal(c.lastResult.reason, 'restart_tui_required');
  assert.deepEqual(messages, ['已定位原终端，但未能自动切回目标会话。已停止按键操作，请手动选择该会话。 • 03:04:05']);
  console.log('PASS: terminal/TUI exit, history, duplicate events, cross-window protection, reload does not clear, click message timestamp');
})().catch(e => { console.error(e); process.exitCode = 1; }).finally(() => fs.rmSync(root, { recursive: true, force: true }));
