'use strict';

const vscode = require('vscode');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const { randomUUID } = require('node:crypto');
const { execFile } = require('node:child_process');
const { ClickBridge } = require('./click');

const FULL_ID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const TITLE_ID = /^([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-(?:[0-9a-f]{12}|[0-9a-f]{5}\.\.\.))(?:\s+[^\x00-\x7f]+)?$/;

function titlePrefix(name) {
  if (typeof name !== 'string') return null;
  const parts = name.split(' | ').map(item => item.trim());
  const app = parts.indexOf('codex');
  if (app < 0 || app + 1 >= parts.length) return null;
  const match = parts[app + 1].match(TITLE_ID);
  return match ? match[1].replace(/\.\.\.$/, '') : null;
}

let stop;

function activate(context) {
  const output = vscode.window.createOutputChannel('Codex Notifications');
  context.subscriptions.push(output);
  const windowId = randomUUID();
  const terminalIds = new WeakMap();
  const commandTitles = new WeakMap();
  let nextTerminalId = 0;
  let generation = 0;
  let key = null;
  let prefix = null;
  let threadId = null;
  let resolving = false;
  let focused = false;
  let terminal = null;
  let lastWrite = 0;
  let lastResolve = 0;
  let disposed = false;
  let statePath;
  let home;
  let lastError = '';
  let lastErrorTime = 0;
  const children = new Set();
  let click;

  function report(message) {
    if (message !== lastError || Date.now() - lastErrorTime > 30000) {
      output.appendLine(`${new Date().toISOString()} ${message}`);
      lastError = message;
      lastErrorTime = Date.now();
    }
  }

  function removeState() {
    if (!statePath) return;
    try { fs.unlinkSync(statePath); } catch (error) {
      if (error.code !== 'ENOENT') report(`State cleanup: ${error.code}`);
    }
  }

  function setHome() {
    removeState();
    const configured = vscode.workspace.getConfiguration('codexFocus').get('codexHome');
    let installedHome;
    try { installedHome = JSON.parse(fs.readFileSync(path.join(os.homedir(), '.local/share/codex-focus-notifications/active-home.json'), 'utf8')).home; } catch {}
    const value = configured || process.env.CODEX_HOME || installedHome || path.join(os.homedir(), '.codex');
    home = path.resolve(value.replace(/^~(?=\/|$)/, os.homedir()));
    statePath = path.join(home, 'vscode-focus', `${windowId}.json`);
    if (click) click.reset(home);
    generation++;
    key = null;
    prefix = null;
    threadId = null;
    resolving = false;
  }

  function publish() {
    if (disposed || !statePath) return;
    const temporary = `${statePath}.tmp`;
    try {
      fs.mkdirSync(path.dirname(statePath), { recursive: true, mode: 0o700 });
      fs.writeFileSync(temporary, JSON.stringify({
        version: 1, window_id: windowId, pid: process.pid,
        thread_id: click && click.suppressFocus() ? null : threadId,
        thread_prefix: click && click.suppressFocus() ? null : prefix,
        focused: focused && !(click && click.suppressFocus()), updated_at_ms: Date.now()
      }) + '\n', { mode: 0o600 });
      fs.renameSync(temporary, statePath);
      lastWrite = Date.now();
      return true;
    } catch (error) {
      removeState();
      try { fs.unlinkSync(temporary); } catch {}
      report(`State write: ${error.code}`);
      return false;
    }
  }

  function runtime() {
    try { return JSON.parse(fs.readFileSync(path.join(home, 'notification-bridge', 'runtime.json'), 'utf8')); }
    catch { return {}; }
  }
  function helper(args, input, callback, timeout = 2500) {
    const child = execFile(runtime().python || 'python3', [path.join(home, 'scripts', 'codex-focus-notify.py'), ...args], {
      env: { ...process.env, CODEX_HOME: home }, timeout,
      maxBuffer: 8192, windowsHide: true
    }, (error, stdout) => {
      children.delete(child);
      if (disposed) return;
      if (error) report(`Notification helper: ${error.code || error.signal || error.name}`);
      if (callback) callback(error, stdout);
    });
    children.add(child);
    child.stdin.on('error', () => {});
    child.stdin.end(input === undefined ? '' : JSON.stringify(input));
  }

  function clearCurrent() {
    if (focused && threadId && !(click && click.suppressFocus())) {
      helper(['--vscode-clear'], { window_id: windowId, thread_id: threadId });
    }
  }

  function resolveCurrent() {
    if (!prefix || resolving || disposed) return;
    const version = generation;
    const requested = prefix;
    lastResolve = Date.now();
    resolving = true;
    helper(['--resolve-thread', requested], undefined, (error, stdout) => {
      if (generation !== version) return;
      resolving = false;
      if (error) return;
      try {
        const resolved = JSON.parse(stdout).thread_id;
        if (typeof resolved !== 'string' || !FULL_ID.test(resolved) || !resolved.startsWith(requested)) return;
        threadId = resolved;
        if (!sample()) return;
        if (publish()) clearCurrent();
      } catch { report('Session ID unavailable; keeping normal notifications.'); }
    });
  }

  function sample() {
    if (disposed) return false;
    const active = vscode.window.activeTerminal;
    const observed = active && commandTitles.get(active);
    const nextPrefix = observed ? observed.prefix : (active ? titlePrefix(active.name) : null);
    if (active && nextPrefix) click.title(active, nextPrefix);
    if (active && !terminalIds.has(active)) terminalIds.set(active, ++nextTerminalId);
    const nextFocused = process.platform === 'darwin' && !vscode.env.remoteName
      && vscode.window.state.focused === true;
    const nextKey = `${nextFocused}:${active ? terminalIds.get(active) : 0}:${nextPrefix || ''}`;
    if (nextKey === key) return true;
    const sameSession = active === terminal && nextPrefix === prefix;
    generation++;
    resolving = false;
    key = nextKey;
    terminal = active;
    focused = nextFocused;
    prefix = nextPrefix;
    if (!sameSession) threadId = null;
    publish();
    if (threadId) clearCurrent();
    else resolveCurrent();
    return false;
  }

  function tick() {
    if (disposed) return;
    sample();
    click.tick();
    if (Date.now() - lastWrite >= 1000) publish();
    if (prefix && !threadId && !resolving && Date.now() - lastResolve >= 3000) resolveCurrent();
  }

  async function observeCommand(event) {
    const stream = event.execution.read();
    click.startCommand(event.terminal, event.execution);
    const observed = { prefix: null };
    commandTitles.set(event.terminal, observed);
    tick();
    let tail = '';
    try {
      for await (const chunk of stream) {
        if (disposed || commandTitles.get(event.terminal) !== observed) break;
        click.feed(event.terminal, chunk);
        const data = tail + chunk;
        const titles = /\x1b\](?:0|2);([^\x07\x1b]*)(?:\x07|\x1b\\)/g;
        let match;
        let end = 0;
        while ((match = titles.exec(data))) {
          observed.prefix = titlePrefix(match[1]);
          click.title(event.terminal, observed.prefix);
          end = titles.lastIndex;
        }
        const pending = data.lastIndexOf('\x1b]');
        tail = pending >= end && data.length - pending <= 2048
          ? data.slice(pending) : (data.endsWith('\x1b') ? '\x1b' : '');
        tick();
      }
    } catch { report('Terminal output observation unavailable; keeping normal notifications.'); }
    finally {
      if (commandTitles.get(event.terminal) === observed) {
        click.endCommand(event.terminal, event.execution);
        observed.prefix = null;
        tick();
      }
    }
  }

  click = new ClickBridge({ vscode, windowId, log: report,
    debug: context.extensionMode === vscode.ExtensionMode.Test,
    changed: () => { key = null; tick(); },
    codex: () => vscode.workspace.getConfiguration('codexFocus').get('codexPath') || runtime().codex || 'codex',
    closed: ids => { if (!disposed) helper(['--vscode-clear-closed'], { thread_ids: ids }, undefined, Math.max(2500, ids.length * 2100 + 1000)); },
    resolve: value => new Promise((resolve, reject) => {
      helper(['--resolve-thread', value], undefined, (error, stdout) => {
        if (error) { reject(error); return; }
        try { resolve(JSON.parse(stdout).thread_id); } catch (failure) { reject(failure); }
      });
    }) });
  setHome();
  const interval = setInterval(tick, 250);
  interval.unref();
  context.subscriptions.push(
    vscode.window.onDidChangeWindowState(tick),
    vscode.window.onDidChangeActiveTerminal(tick),
    vscode.window.onDidCloseTerminal(value => { click.closeTerminal(value); tick(); }),
    vscode.window.onDidEndTerminalShellExecution(event => { click.endCommand(event.terminal, event.execution); tick(); }),
    vscode.window.onDidStartTerminalShellExecution(event => { void observeCommand(event); }),
    vscode.workspace.onDidChangeConfiguration(event => {
      if (event.affectsConfiguration('codexFocus.codexHome')) { setHome(); tick(); }
    }),
    vscode.commands.registerCommand('codexFocus.showStatus', () => {
      tick();
      output.appendLine(JSON.stringify({ window_id: windowId, focused, thread_id: threadId,
        recognized_title: Boolean(prefix), state_file: statePath,
        click: click.status(),
        remote_window: Boolean(vscode.env.remoteName) }, null, 2));
      output.appendLine('Runtime: ' + JSON.stringify({ configured: Boolean(runtime().python), codex: runtime().codex || 'PATH' }));
      output.show(true);
    })
  );
  stop = () => {
    if (disposed) return;
    disposed = true;
    click.dispose();
    generation++;
    clearInterval(interval);
    for (const child of children) child.kill();
    children.clear();
    removeState();
  };
  context.subscriptions.push({ dispose: stop });
  output.appendLine('Active: focused VS Code window + selected terminal. Unknown sessions keep normal notifications.');
  tick();
  if (context.extensionMode === vscode.ExtensionMode.Test) return {
    getClickStatus: () => click.status(), getClickScreen: () => click.debugScreen(),
    getLiveScreen: () => click.debugScreens?.get(vscode.window.activeTerminal)?.text()
  };
}

function deactivate() { if (stop) stop(); }

module.exports = { activate, deactivate };
