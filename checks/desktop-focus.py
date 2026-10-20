"""Disposable integration check in an isolated VS Code window, without a model."""
from pathlib import Path
import json
import shlex
import sys
import os
import shutil
import signal
import subprocess
import tempfile
import time

root = Path(__file__).resolve().parents[1]
(root / "dist").mkdir(exist_ok=True)
codex = os.environ.get("CODEX_SMOKE_CODEX") or shutil.which("codex")
if not codex: raise SystemExit("需要 CODEX_SMOKE_CODEX 或 PATH 中的 codex")
notifier = os.environ.get("CODEX_SMOKE_NOTIFIER") or shutil.which("terminal-notifier")
if not notifier: raise SystemExit("需要 terminal-notifier")
ids = ["f013e470-0000-0000-0000-000000000001", "f013e470-0000-0000-0000-111111111112"]
runner = r'''
const vscode = require('vscode');
const fs = require('node:fs');
const path = require('node:path');
const { execFileSync } = require('node:child_process');
const home = process.env.CODEX_HOME;
const ids = ['f013e470-0000-0000-0000-000000000001','f013e470-0000-0000-0000-111111111112'];
const notifier = process.env.CODEX_SMOKE_NOTIFIER;
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
function assert(ok, message) { if (!ok) throw new Error(message); }
function notifications(id) { return execFileSync(notifier, ['-list','codex-'+id],{encoding:'utf8'}); }
function post(id) {
 const script='import importlib.util,sys; s=importlib.util.spec_from_file_location("n",sys.argv[1]); n=importlib.util.module_from_spec(s); s.loader.exec_module(n); n.send_notification("/tmp/example-project",sys.argv[2],"Focus notification smoke test")';
 execFileSync(process.env.CODEX_SMOKE_PYTHON||'python3',['-c',script,path.join(home,'scripts','codex-focus-notify.py'),id],{env:{...process.env,CODEX_HOME:home}});
}
function state(includeBackground=false) {
 try { return fs.readdirSync(path.join(home,'vscode-focus')).filter(x=>x.endsWith('.json')).map(x=>JSON.parse(fs.readFileSync(path.join(home,'vscode-focus',x),'utf8'))).find(x=>includeBackground || x.focused); } catch { return undefined; }
}
async function until(test, message) {
 const end=Date.now()+12000;
 while(Date.now()<end) { if(test()) return; await sleep(100); }
 throw new Error(message+'; state='+JSON.stringify(state())+'; terminals='+vscode.window.terminals.map(t=>t.name));
}
exports.run = async () => {
 let term;
 try {
  const extension=vscode.extensions.getExtension('frequenk.codex-focus-notifications');
  assert(extension,'development extension missing');await extension.activate();
  await vscode.commands.executeCommand('workbench.action.focusWindow');
  await until(()=>vscode.window.state.focused,'test window did not gain focus');
  post(ids[0]);post(ids[1]);
  await until(()=>notifications(ids[0]).includes(ids[0]) && notifications(ids[1]).includes(ids[1]),'background notifications not delivered');
  term=vscode.window.createTerminal({shellPath:'/bin/zsh',shellArgs:['-f']});term.show();
  const program=['import sys', 'a="'+ids[0].slice(0,29)+'..."', 'b="'+ids[1].slice(0,29)+'..."',
   'def emit(v):', ' sys.stdout.write(chr(27)+"]0;codex | "+v+" | Focus smoke"+chr(7));sys.stdout.flush()',
   'emit(a)', 'for line in sys.stdin:', ' emit(b if line.strip()=="B" else a)'].join(String.fromCharCode(10));
  const command='exec('+JSON.stringify(program)+')';
  term.sendText("python3 -u -c '"+command.replace(/'/g,"'\\''")+"'");
  await until(()=>state()?.thread_id===ids[0],'title A was not recognized');
  await until(()=>!notifications(ids[0]).includes(ids[0]),'focus did not clear A');
  assert(notifications(ids[1]).includes(ids[1]),'focus A incorrectly cleared B');
  post(ids[0]);assert(!notifications(ids[0]).includes(ids[0]),'foreground A was not suppressed');
  term.sendText('B');
  await until(()=>state()?.thread_id===ids[1],'same terminal switch A to B was not recognized');
  await until(()=>!notifications(ids[1]).includes(ids[1]),'switch did not clear B');
  post(ids[0]);await until(()=>notifications(ids[0]).includes(ids[0]),'background A was suppressed');
  post(ids[1]);assert(!notifications(ids[1]).includes(ids[1]),'foreground B was not suppressed');
  term.dispose();term=undefined;
  await until(()=>!state()?.thread_id,'closing terminal left foreground session');
  post(ids[1]);await until(()=>notifications(ids[1]).includes(ids[1]),'closed terminal still suppressed B');
  await vscode.workspace.getConfiguration('terminal.integrated.tabs').update('title','${process}',vscode.ConfigurationTarget.Global);
  await vscode.workspace.getConfiguration('terminal.integrated.shellIntegration').update('enabled',true,vscode.ConfigurationTarget.Global);
  term=vscode.window.createTerminal({shellPath:'/bin/zsh',cwd:home});term.show();
  await until(()=>term.shellIntegration,'shell integration did not activate');
  term.sendText('CODEX_HOME='+JSON.stringify(home)+' '+process.env.CODEX_SMOKE_CODEX_Q+' -c check_for_update_on_startup=false resume '+ids[0]);
  await until(()=>state(true)?.thread_id===ids[0],'unmodified Codex resume was not recognized with default VS Code agent title policy');
  fs.writeFileSync(process.env.CODEX_SMOKE_RESULT,JSON.stringify({result:'PASS',checks:['real VS Code terminal OSC title -> truncated ID resolution','focus clears A and preserves B','foreground suppression','same terminal A -> B clears B and preserves background A','terminal close restores normal notification','unmodified Codex CLI recognized with default VS Code title settings; no model messages sent']},null,2));
 } catch(error) {
  fs.writeFileSync(process.env.CODEX_SMOKE_RESULT,JSON.stringify({result:'FAIL',error:error.stack,state:state(true)},null,2));throw error;
 } finally {
  if(term)term.dispose();
  for(const id of ids)execFileSync(notifier,['-remove','codex-'+id]);
 }
};
'''

with tempfile.TemporaryDirectory(prefix="codex-vscode-smoke-") as temp:
    t = Path(temp)
    home = t / "codex"
    (home / "scripts").mkdir(parents=True)
    shutil.copy2(root / 'scripts/notify.py', home / 'scripts/codex-focus-notify.py')
    (home / 'notification-bridge').mkdir()
    (home / 'notification-bridge/runtime.json').write_text(json.dumps({'python': sys.executable, 'codex': codex, 'notifier': notifier}))
    (home / "config.toml").write_text('model = "gpt-6.1-sol"\nmodel_provider = "fixture"\n[model_providers.fixture]\nname="Local fixture"\nbase_url="http://127.0.0.1:9/v1"\nwire_api="responses"\nrequires_openai_auth=false\n'
        '[tui]\nterminal_title = ["app-name", "thread-id", "thread-name"]\nscreen_reader_detection_done = true\n'
        '[projects.' + json.dumps(str(home)) + ']\ntrust_level = "trusted"\n'
        '[projects.' + json.dumps(str(home.resolve())) + ']\ntrust_level = "trusted"\n')
    (home / "session_index.jsonl").write_text("".join(
        json.dumps({"id": value, "thread_name": "Smoke " + str(i)}) + "\n" for i, value in enumerate(ids)))
    sessions = home / "sessions/2026/10/20"
    sessions.mkdir(parents=True)
    (sessions / ("rollout-2026-10-20T08-00-00-" + ids[0] + ".jsonl")).write_text(json.dumps({
        "timestamp": "2026-10-20T00:00:00Z", "type": "session_meta", "payload": {
            "id": ids[0], "session_id": ids[0], "timestamp": "2026-10-20T00:00:00Z",
            "cwd": str(home.resolve()), "originator": "codex_cli_rs", "cli_version": "0.163.0",
            "source": "cli", "model_provider": "fixture"}}) + "\n")
    user = t / "data/User"
    user.mkdir(parents=True)
    (user / "settings.json").write_text(json.dumps({
        "codexFocus.codexHome": str(home), "security.workspace.trust.enabled": False,
        "telemetry.telemetryLevel": "off", "update.mode": "none", "extensions.autoUpdate": False,
        "workbench.startupEditor": "none", "window.restoreWindows": "none",
        "terminal.integrated.shellIntegration.enabled": False,
        "terminal.integrated.tabs.title": "${sequence}"}))
    (t / "smoke.js").write_text(runner)
    result = t / "result.json"
    env = dict(os.environ, CODEX_HOME=str(home), CODEX_SMOKE_PYTHON=sys.executable, CODEX_SMOKE_CODEX_Q=shlex.quote(codex), CODEX_SMOKE_RESULT=str(result), CODEX_SMOKE_NOTIFIER=notifier)
    for name in ("ELECTRON_RUN_AS_NODE", "VSCODE_IPC_HOOK_CLI"):
        env.pop(name, None)
    command = ["/Applications/Visual Studio Code.app/Contents/MacOS/Code", "--new-window",
               "--user-data-dir=" + str(t / "data"), "--extensions-dir=" + str(t / "extensions"),
               "--extensionDevelopmentPath=" + str(root), "--extensionTestsPath=" + str(t / "smoke.js"),
               "--disable-extensions", "--skip-welcome", "--skip-release-notes", "--disable-workspace-trust"]
    with (t / "output.log").open("w") as log:
        process = subprocess.Popen(command, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        time.sleep(2)
        subprocess.run(['/usr/bin/osascript', '-l', 'JavaScript', '-e',
            "ObjC.import('AppKit'); $.NSRunningApplication.runningApplicationWithProcessIdentifier(" + str(process.pid) + ").activateWithOptions(3)"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
        try:
            deadline = time.monotonic() + 65
            while time.monotonic() < deadline and not result.exists() and process.poll() is None:
                time.sleep(0.2)
            if result.exists():
                time.sleep(1)
                payload = json.loads(result.read_text())
                (root / "dist" / "smoke-result.json").write_text(result.read_text())
                print(json.dumps(payload, ensure_ascii=False), flush=True)
                if payload["result"] != "PASS":
                    raise SystemExit(1)
            else:
                log.flush()
                print("VS Code did not complete smoke test; exit=" + str(process.poll()), flush=True)
                print((t / "output.log").read_text()[-5000:], flush=True)
                raise SystemExit(1)
        finally:
            if process.poll() is None:
                
                try: os.killpg(process.pid, signal.SIGTERM)
                except (ProcessLookupError, PermissionError): pass
                try:
                    process.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
            for value in ids:
                subprocess.run([notifier, "-remove", "codex-" + value], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
