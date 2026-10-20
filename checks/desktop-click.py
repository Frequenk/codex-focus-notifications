"""Isolated real-TUI click check; busy turns use only a temporary local SSE stub."""
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import shlex
import sys
import os
import shutil
import signal
import subprocess
import tempfile
import threading
import time

root = Path(__file__).resolve().parents[1]
(root / "dist").mkdir(exist_ok=True)
codex = os.environ.get("CODEX_SMOKE_CODEX") or shutil.which("codex")
if not codex: raise SystemExit("需要 CODEX_SMOKE_CODEX 或 PATH 中的 codex")
notifier = os.environ.get("CODEX_SMOKE_NOTIFIER") or shutil.which("terminal-notifier")
if not notifier: raise SystemExit("需要 terminal-notifier")
ids = ['f023e470-0000-0000-0000-000000000001', 'f023e470-0000-0000-0000-111111111112',
       'f023e470-0000-0000-0000-222222222223', 'f023e470-0000-0000-0000-333333333334']

runner = r'''
const vscode=require('vscode'); const fs=require('node:fs'); const path=require('node:path');
const {execFileSync}=require('node:child_process');
const home=process.env.CODEX_HOME; const ids=JSON.parse(process.env.CLICK_SMOKE_IDS);
let api; const terms=[]; const sleep=ms=>new Promise(r=>setTimeout(r,ms));
function state(){try{return fs.readdirSync(path.join(home,'vscode-focus')).filter(x=>x.endsWith('.json')).map(x=>JSON.parse(fs.readFileSync(path.join(home,'vscode-focus',x),'utf8'))).find(x=>x.thread_id);}catch{return undefined;}}
function assert(value,message){if(!value)throw Error(message);}
async function until(test,message,timeout=20000){const end=Date.now()+timeout;while(Date.now()<end){if(test())return;await sleep(50);}throw Error(message+'; state='+JSON.stringify(state())+'; click='+JSON.stringify(api?.getClickStatus()));}
function py(args){return execFileSync(process.env.CODEX_SMOKE_PYTHON||'python3',[path.join(home,'scripts/codex-focus-notify.py'),...args],{env:{...process.env,CODEX_HOME:home},encoding:'utf8'});}
function post(id){execFileSync(process.env.CODEX_SMOKE_PYTHON||'python3',['-B','-c','import importlib.util,sys;s=importlib.util.spec_from_file_location("n",sys.argv[1]);n=importlib.util.module_from_spec(s);s.loader.exec_module(n);n.send_notification("/tmp/example-project",sys.argv[2],"Click smoke test")',path.join(home,'scripts/codex-focus-notify.py'),id],{env:{...process.env,CODEX_HOME:home}});}
function registry(){try{return fs.readdirSync(path.join(home,'vscode-click/windows')).flatMap(n=>JSON.parse(fs.readFileSync(path.join(home,'vscode-click/windows',n),'utf8')).terminals);}catch{return [];}}
async function click(id){
 post(id);let ticket;
 await until(()=>{const d=path.join(home,'vscode-click/tickets');if(!fs.existsSync(d))return false;ticket=fs.readdirSync(d).find(n=>n.endsWith('.json')&&JSON.parse(fs.readFileSync(path.join(d,n),'utf8')).thread_id===id);return !!ticket;},'click ticket missing');
 py(['--open-notification',ticket.slice(0,-5)]);
 const result=path.join(home,'vscode-click/results',ticket);
 await until(()=>fs.existsSync(result),'click result missing',15000);
 return JSON.parse(fs.readFileSync(result,'utf8'));
}
exports.run=async()=>{
 try{
  api=await vscode.extensions.getExtension('frequenk.codex-focus-notifications').activate();
  await vscode.commands.executeCommand('workbench.action.focusWindow');
  const term=vscode.window.createTerminal({shellPath:'/bin/zsh',cwd:home});terms.push(term);term.show();
  await until(()=>term.shellIntegration,'shell integration unavailable');
  term.sendText('CODEX_HOME='+JSON.stringify(home)+' '+process.env.CODEX_SMOKE_CODEX_Q+' -c check_for_update_on_startup=false resume --remote unix://'+process.env.CLICK_SMOKE_SOCKET+' '+ids[0]);
  await until(()=>state()?.thread_id===ids[0],'native A did not start');
  await until(()=>registry().some(t=>t.thread_ids.includes(ids[0])),'native A route missing');
  await sleep(800);
  term.sendText('/resume '+ids[1],false);await sleep(350);term.sendText('\x1b[13u',false);
  await until(()=>state()?.thread_id===ids[1],'native B did not open');
  await until(()=>registry().some(t=>t.thread_ids.includes(ids[0])&&t.thread_ids.includes(ids[1])),'history route missing');
  term.sendText('LOCAL MOCK BUSY TURN',false);await sleep(350);term.sendText('\x1b[13u',false);
  await until(()=>JSON.parse(fs.readFileSync(process.env.CLICK_SMOKE_SERVER_STATE,'utf8')).posts===1,'local mock request not started');
  term.sendText('DRAFT-KEEP-UNSENT',false);
  const other=vscode.window.createTerminal({name:'Unrelated shell',shellPath:'/bin/zsh',shellArgs:['-f']});terms.push(other);other.show();
  await until(()=>vscode.window.activeTerminal===other,'other terminal not selected');
  const a=await click(ids[0]);assert(a.result==='opened','click A failed: '+JSON.stringify(a));
  assert(vscode.window.activeTerminal===term,'click selected wrong terminal');
  await until(()=>state()?.thread_id===ids[0],'click A did not select A');
  await sleep(1200);
  assert(!JSON.parse(fs.readFileSync(process.env.CLICK_SMOKE_SERVER_STATE,'utf8')).disconnected,'switch interrupted B');
  const busy=await click(ids[1]);assert(busy.result==='failed'&&busy.reason==='target_task_busy','busy target was not rejected before navigation');
  fs.writeFileSync(process.env.CLICK_SMOKE_FINISH,'finish');await sleep(1500);
  const b=await click(ids[1]);assert(b.result==='opened','click B failed: '+JSON.stringify(b));
  const restored=api.getClickScreen();
  assert(restored.lastIndexOf('DRAFT-KEEP-UNSENT')>restored.lastIndexOf('Working')
    && !restored.includes('Ask Codex to do anything'),'B draft was not restored in the composer');
  const mock=JSON.parse(fs.readFileSync(process.env.CLICK_SMOKE_SERVER_STATE,'utf8'));
  assert(mock.posts===1&&!mock.disconnected,'navigation submitted an extra turn or interrupted B');
  const {targetIdentity}=require(path.join(process.env.CLICK_SMOKE_SOURCE,'server'));
  let ambiguous=false;try{await targetIdentity(home,{commandLine:{value:'codex --remote unix://'+process.env.CLICK_SMOKE_SOCKET}},ids[2]);}catch(e){ambiguous=e.message==='ambiguous_session_name';}
  assert(ambiguous,'duplicate names were not rejected');
  const fake=vscode.window.createTerminal({shellPath:'/bin/zsh',cwd:home});terms.push(fake);fake.show();
  await until(()=>fake.shellIntegration,'guard terminal shell integration unavailable');
  const program=['import sys,os,time,tty,pathlib','tty.setraw(0)',
   'def emit(v):',' sys.stdout.write(chr(27)+"]0;codex | "+v[:29]+"... | guard"+chr(7));sys.stdout.flush()',
   'emit("'+ids[2]+'")','time.sleep(0.5)','emit("'+ids[3]+'")',
   'while True:',' data=os.read(0,128)',' with open(os.environ["CLICK_SMOKE_KEYS"],"ab") as f:f.write(data)'].join(String.fromCharCode(10));
  fake.sendText("python3 -u -c '"+('exec('+JSON.stringify(program)+')').replace(/'/g,"'\\''")+"'");
  await until(()=>registry().some(t=>t.thread_ids.includes(ids[2])&&t.thread_ids.includes(ids[3])),'guard history missing');
  const guard=await click(ids[2]);assert(guard.result==='failed'&&guard.stage==='metadata','guard did not fail closed');
  const keys=fs.existsSync(process.env.CLICK_SMOKE_KEYS)?fs.readFileSync(process.env.CLICK_SMOKE_KEYS):Buffer.alloc(0);
  assert(keys.length===0,'guard sent text or Enter outside confirmed UI');
  fs.writeFileSync(process.env.CLICK_SMOKE_RESULT,JSON.stringify({result:'PASS',checks:['native shared-server TUI A -> B -> notification callback -> A','busy B continues in background; reattach deferred until idle','exact original terminal selected','switch back restores unsent B draft','no extra model turns; only local SSE stub used','duplicate names rejected; unavailable metadata stops before any key']},null,2));
 }catch(error){fs.writeFileSync(process.env.CLICK_SMOKE_RESULT,JSON.stringify({result:'FAIL',error:error.stack,click:api?.getClickStatus(),screen:api?.getClickScreen()},null,2));throw error;}
 finally{for(const t of terms)t.dispose();for(const id of ids)execFileSync(process.env.CLICK_SMOKE_NOTIFIER,['-remove','codex-'+id]);}
};
'''

with tempfile.TemporaryDirectory(prefix='codex-click-smoke-', dir='/tmp') as temp:
    t = Path(temp); home = t/'codex'; (home/'scripts').mkdir(parents=True)
    shutil.copy2(root / 'scripts/notify.py', home / 'scripts/codex-focus-notify.py')
    (home / 'notification-bridge').mkdir()
    (home / 'notification-bridge/runtime.json').write_text(json.dumps({'python': sys.executable, 'codex': codex, 'notifier': notifier}))
    server_state = t/'mock-state.json'; status = {'posts': 0, 'disconnected': False}; stop = threading.Event()
    def save_state():
        tmp = server_state.with_suffix('.tmp'); tmp.write_text(json.dumps(status)); tmp.replace(server_state)
    save_state()
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_): pass
        def do_GET(self):
            self.send_response(200); self.send_header('Content-Type', 'application/json'); self.end_headers()
            self.wfile.write(b'{"object":"list","data":[]}')
        def do_POST(self):
            self.rfile.read(int(self.headers.get('Content-Length', '0')))
            status['posts'] += 1; save_state()
            self.send_response(200); self.send_header('Content-Type', 'text/event-stream'); self.end_headers()
            event = {'type': 'response.created', 'response': {'id':'resp_local_smoke', 'status':'in_progress','output':[]}}
            try:
                self.wfile.write(('event: response.created\ndata: '+json.dumps(event)+'\n\n').encode()); self.wfile.flush()
                while not stop.wait(0.25):
                    if (t/'finish').exists():
                        event = {'type':'response.completed','response':{'id':'resp_local_smoke','status':'completed','output':[], 'usage':{'input_tokens':1,'output_tokens':0,'total_tokens':1}}}
                        self.wfile.write(('event: response.completed\ndata: '+json.dumps(event)+'\n\n').encode());self.wfile.flush();break
                    self.wfile.write(b': heartbeat\n\n'); self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError): status['disconnected'] = True; save_state()
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler); server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    (home/'config.toml').write_text('model = "gpt-6.1-sol"\nmodel_provider = "click-smoke"\n'
        '[model_providers.click-smoke]\nname = "Local click smoke"\nbase_url = "http://127.0.0.1:'+str(server.server_port)+'/v1"\nwire_api = "responses"\nrequires_openai_auth = false\n'
        '[tui]\nterminal_title = ["app-name", "thread-id", "thread-name"]\nscreen_reader_detection_done = true\n'
        '[tui.keymap.global]\nopen_agents = ["f12"]\n'
        '[projects.'+json.dumps(str(home.resolve()))+']\ntrust_level = "trusted"\n')
    index=[];sessions=home/'sessions/2026/10/20';sessions.mkdir(parents=True)
    for i, id in enumerate(ids):
        index.append({'id':id,'thread_name':'通知切换测试 '+str(i if i < 2 else 2),'updated_at':'2026-10-20T00:00:00Z'})
        records=[{'timestamp':'2026-10-20T00:00:00Z','type':'session_meta','payload':{
            'id':id,'session_id':id,'timestamp':'2026-10-20T00:00:00Z','cwd':str(home.resolve()),
            'originator':'codex_cli_rs','cli_version':'0.163.0','source':'cli','model_provider':'click-smoke'}},
            {'timestamp':'2026-10-20T00:00:00Z','type':'event_msg','payload':{'type':'user_message','message':'Local click fixture '+str(i),'images':[],'local_images':[],'text_elements':[]}},
            {'timestamp':'2026-10-20T00:00:00Z','type':'response_item','payload':{'type':'message','role':'user','content':[{'type':'input_text','text':'Local click fixture '+str(i)}]}},
            {'timestamp':'2026-10-20T00:00:01Z','type':'response_item','payload':{'type':'message','role':'assistant','content':[{'type':'output_text','text':'Ready.'}],'phase':'final_answer'}}]
        (sessions/('rollout-2026-10-20T08-00-0'+str(i)+'-'+id+'.jsonl')).write_text(''.join(json.dumps(r)+'\n' for r in records))
    (home/'session_index.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in index))
    user=t/'data/User';user.mkdir(parents=True)
    (user/'settings.json').write_text(json.dumps({'codexFocus.codexHome':str(home),'security.workspace.trust.enabled':False,
        'telemetry.telemetryLevel':'off','update.mode':'none','extensions.autoUpdate':False,'workbench.startupEditor':'none',
        'window.restoreWindows':'none','terminal.integrated.shellIntegration.enabled':True}))
    (t/'test.js').write_text(runner); result=t/'result.json'
    env=dict(os.environ,CODEX_HOME=str(home), CODEX_SMOKE_PYTHON=sys.executable, CODEX_SMOKE_CODEX_Q=shlex.quote(codex),CLICK_SMOKE_IDS=json.dumps(ids),CLICK_SMOKE_RESULT=str(result),
        CLICK_SMOKE_SERVER_STATE=str(server_state),CLICK_SMOKE_KEYS=str(t/'keys.bin'),CLICK_SMOKE_NOTIFIER=notifier,
        CLICK_SMOKE_SOCKET=str(t/'server.sock'), CLICK_SMOKE_SOURCE=str(root/'src'), CLICK_SMOKE_FINISH=str(t/'finish'))
    for name in ['ELECTRON_RUN_AS_NODE','VSCODE_IPC_HOOK_CLI']:env.pop(name,None)
    native_log=(t/'app-server.log').open('w')
    native=subprocess.Popen([codex,'app-server','--listen','unix://'+str(t/'server.sock')],
        env=env,stdout=native_log,stderr=subprocess.STDOUT,start_new_session=True)
    ready=time.monotonic()+10
    while time.monotonic()<ready and not (t/'server.sock').exists() and native.poll() is None:time.sleep(0.05)
    args=['/Applications/Visual Studio Code.app/Contents/MacOS/Code','--new-window','--user-data-dir='+str(t/'data'),
        '--extensions-dir='+str(t/'extensions'),'--extensionDevelopmentPath='+str(root),
        '--extensionTestsPath='+str(t/'test.js'),'--disable-extensions','--skip-welcome','--skip-release-notes','--disable-workspace-trust']
    with (t/'output.log').open('w') as log:
        process=subprocess.Popen(args,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        time.sleep(2)
        subprocess.run(['/usr/bin/osascript', '-l', 'JavaScript', '-e',
            "ObjC.import('AppKit'); $.NSRunningApplication.runningApplicationWithProcessIdentifier(" + str(process.pid) + ").activateWithOptions(3)"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
        try:
            end=time.monotonic()+105
            while time.monotonic()<end and not result.exists() and process.poll() is None:time.sleep(0.2)
            if result.exists():
                time.sleep(0.5);payload=json.loads(result.read_text());(root/'dist'/'click-smoke-result.json').write_text(result.read_text())
                print(json.dumps(payload,ensure_ascii=False),flush=True)
                if payload['result']!='PASS':
                    traces={str(f.relative_to(t)):f.read_text(errors='replace')[-10000:] for f in t.rglob('*.log') if 'codex/log' in str(f) or f.name=='app-server.log'}
                    (root/'dist'/'click-debug.json').write_text(json.dumps(traces,indent=2))
                    raise SystemExit(1)
            else:
                log.flush();print((t/'output.log').read_text()[-3000:],flush=True);raise SystemExit('No integration result')
        finally:
            if process.poll() is None:
                
                try:os.killpg(process.pid,signal.SIGTERM)
                except (ProcessLookupError, PermissionError):pass
                try:process.wait(timeout=6)
                except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait()
            if native.poll() is None:
                os.killpg(native.pid,signal.SIGTERM)
                try:native.wait(timeout=3)
                except subprocess.TimeoutExpired:os.killpg(native.pid,signal.SIGKILL);native.wait()
            native_log.close()
            stop.set();server.shutdown();server.server_close()
            for id in ids:subprocess.run([notifier,'-remove','codex-'+id],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
