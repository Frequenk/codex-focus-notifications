#!/usr/bin/env python3
"""供 agent 调用的安装、诊断与恢复入口。"""
import argparse
import ast
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import plistlib
import shlex
import shutil
import subprocess
import sys
import tempfile
import zipfile
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'vendor'))
ID = 'frequenk.codex-focus-notifications'
VERSION = json.loads((ROOT / 'package.json').read_text())['version']
MISSING = {'missing': True}


def run(argv):
    return subprocess.check_output([str(v) for v in argv], text=True, stderr=subprocess.PIPE, timeout=180).strip()


def private_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temp = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump(value, f, ensure_ascii=False, indent=2)
            f.write('\n')
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def executable(value, fallback):
    candidate = value or shutil.which(fallback)
    if not candidate:
        return None
    return str(Path(candidate).expanduser().absolute())


def environment(args):
    return {'platform': sys.platform, 'python': sys.executable,
            'codex': executable(args.codex_bin, 'codex'),
            'code': executable(args.code_bin, 'code'),
            'notifier': executable(args.notifier_bin, 'terminal-notifier'),
            'brew': shutil.which('brew'), 'codex_home': str(args.home), 'version': VERSION}


def toml_module():
    try:
        import tomlkit
        return tomlkit
    except ImportError:
        raise RuntimeError('缺少安装依赖；请使用 Release 安装工具包，或安装 requirements-build.txt')


def plain(value):
    return json.loads(json.dumps(value.unwrap() if hasattr(value, 'unwrap') else value))


def get_key(doc, keys):
    current = doc
    for key in keys:
        if key not in current:
            return MISSING
        current = current[key]
    return plain(current)


def set_key(doc, keys, value):
    current = doc
    for key in keys[:-1]:
        if key not in current:
            current[key] = toml_module().table()
        current = current[key]
    if value == MISSING:
        current.pop(keys[-1], None)
    else:
        current[keys[-1]] = value


def legacy_callback(command):
    if not isinstance(command, list):
        raise RuntimeError('现有 notify 不是命令数组，停止自动覆盖')
    for argument in command:
        if not isinstance(argument, str) or not argument.endswith('.py'):
            continue
        path = Path(argument)
        if not path.is_file():
            continue
        text = path.read_text()
        if 'def is_session_foreground(' in text and 'def handle_clear_hook(' in text:
            for node in ast.parse(text).body:
                if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'ORIGINAL_CALLBACK' for t in node.targets):
                    return ast.literal_eval(node.value), str(path)
    return command, None


def owned_hook(hook, scripts):
    try:
        parts = shlex.split(hook.get('command', ''))
    except ValueError:
        return False
    return hook.get('type') == 'command' and any(p in scripts for p in parts) and any(p in ('--input-hook', '--clear-hook') for p in parts)


def filter_hooks(document, scripts):
    result = json.loads(json.dumps(document))
    for event, groups in list(result.setdefault('hooks', {}).items()):
        kept = []
        for group in groups:
            item = dict(group)
            item['hooks'] = [h for h in group.get('hooks', []) if not owned_hook(h, scripts)]
            if item['hooks']:
                kept.append(item)
        result['hooks'][event] = kept
    return result


def legacy_vsix(folder, target):
    # 旧身份仅写入用户私有备份，不进入公开项目。
    package = json.loads((folder / 'package.json').read_text())
    package.pop('__metadata', None)
    name, publisher, version = (escape(package[k]) for k in ('name', 'publisher', 'version'))
    manifest = f'''<PackageManifest Version="2.0.0" xmlns="http://schemas.microsoft.com/developer/vsx-schema/2011"><Metadata><Identity Language="en-US" Id="{name}" Version="{version}" Publisher="{publisher}"/><DisplayName>Codex Focus Notifications</DisplayName><Description xml:space="preserve">Local backup</Description><Properties><Property Id="Microsoft.VisualStudio.Code.Engine" Value="^1.100.0"/></Properties></Metadata><Installation><InstallationTarget Id="Microsoft.VisualStudio.Code"/></Installation><Dependencies/><Assets><Asset Type="Microsoft.VisualStudio.Code.Manifest" Path="extension/package.json" Addressable="true"/></Assets></PackageManifest>'''
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('extension.vsixmanifest', manifest)
        archive.writestr('[Content_Types].xml', '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="json" ContentType="application/json"/><Default Extension="js" ContentType="application/javascript"/><Default Extension="md" ContentType="text/markdown"/><Default Extension="vsixmanifest" ContentType="text/xml"/></Types>')
        for p in folder.rglob('*'):
            if p.is_file() and p.name != 'package.json':
                archive.write(p, 'extension/' + str(p.relative_to(folder)))
        archive.writestr('extension/package.json', json.dumps(package))


def prepare_app(notifier, target, icon):
    binary = Path(notifier).resolve()
    origin = next((p for p in binary.parents if p.suffix == '.app'), None)
    if not origin:
        candidate = binary.parent.parent / 'terminal-notifier.app'
        if candidate.is_dir(): origin = candidate
    if not origin:
        raise RuntimeError('通知工具必须来自有效的 terminal-notifier.app 或 Homebrew 包装命令')
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = target.with_name(target.name + '.installing')
    if staging.exists():
        shutil.rmtree(staging)
    shutil.copytree(origin, staging)
    info_path = staging / 'Contents/Info.plist'
    info = plistlib.loads(info_path.read_bytes())
    info.update(CFBundleIdentifier='io.github.frequenk.codex-focus-notifications',
                CFBundleName='Codex Focus Notifications', CFBundleDisplayName='Codex Focus Notifications',
                CFBundleIconFile='Focus.icns', LSUIElement=True)
    info_path.write_bytes(plistlib.dumps(info))
    license_file = origin.parent / 'LICENSE.md'
    if license_file.exists(): shutil.copy2(license_file, staging / 'Contents/Resources/terminal-notifier.LICENSE.md')
    for localized in (staging / 'Contents/Resources').glob('*.lproj/InfoPlist.strings'):
        localized.write_text('"CFBundleDisplayName" = "Codex Focus Notifications";\n')
    with tempfile.TemporaryDirectory() as tmp:
        icons = Path(tmp) / 'Focus.iconset'; icons.mkdir()
        for size in (16, 32, 128, 256, 512):
            for factor in (1, 2):
                dest = icons / ('icon_' + str(size) + 'x' + str(size) + ('@2x' if factor == 2 else '') + '.png')
                run(['/usr/bin/sips', '-z', size * factor, size * factor, icon, '--out', dest])
        run(['/usr/bin/iconutil', '-c', 'icns', icons, '-o', staging / 'Contents/Resources/Focus.icns'])
    for name in ('Terminal.icns', 'Codex.icns'):
        (staging / 'Contents/Resources' / name).unlink(missing_ok=True)
    run(['/usr/bin/codesign', '--force', '--deep', '--sign', '-', staging])
    old = target.with_name(target.name + '.previous')
    if old.exists():
        shutil.rmtree(old)
    if target.exists():
        target.rename(old)
    try:
        staging.rename(target)
    except Exception:
        if old.exists() and not target.exists(): old.rename(target)
        raise
    return str(target / 'Contents/MacOS' / info['CFBundleExecutable'])


def install(args, env):
    tk = toml_module()
    base = args.home / 'notification-bridge'
    runtime_file = base / 'runtime.json'; manifest_file = base / 'installed.json'
    previous = json.loads(manifest_file.read_text()) if manifest_file.exists() else None
    config_path = args.home / 'config.toml'; hooks_path = args.home / 'hooks.json'
    doc = tk.parse(config_path.read_text() if config_path.exists() else '')
    hooks = json.loads(hooks_path.read_text()) if hooks_path.exists() else {'hooks': {}}
    script = args.home / 'scripts/codex-focus-notify.py'
    original = get_key(doc, ['notify']); original = [] if original == MISSING else original
    current_command = [env['python'], str(script)]
    if runtime_file.exists() and original == json.loads(runtime_file.read_text()).get('managed_callback'):
        original = json.loads(runtime_file.read_text()).get('original_callback', [])
    original, legacy_script = legacy_callback(original)
    owned = {str(script)} | ({legacy_script} if legacy_script else set())
    if not previous and (script.exists() or runtime_file.exists()):
        raise RuntimeError('发现未登记的运行文件，停止覆盖；请先检查本机安装记录')
    if previous:
        for path, digest in previous.get('hashes', {}).items():
            if not Path(path).is_file() or hashlib.sha256(Path(path).read_bytes()).hexdigest() != digest:
                raise RuntimeError('检测到运行文件被修改，停止覆盖：' + path)
        for change in previous.get('changes', []):
            if get_key(doc, change['keys']) != change['after']:
                raise RuntimeError('检测到受管配置被修改，停止升级：' + '.'.join(change['keys']))
        owned.update(previous.get('owned_scripts', []))
    new_hooks = filter_hooks(hooks, owned)
    command = shlex.join([env['python'], str(script), '--input-hook'])
    input_group = {'matcher': '^request_user_input$', 'hooks': [{'type': 'command', 'command': command, 'timeout': 6}]}
    new_hooks['hooks'].setdefault('PreToolUse', []).append(input_group)
    changes = []
    title = ['app-name', 'thread-id', 'thread-name']
    bindings = get_key(doc, ['tui', 'keymap', 'global', 'open_agents'])
    if bindings == MISSING:
        bindings = ['f12']
    elif isinstance(bindings, list):
        bindings = list(dict.fromkeys(bindings + ['f12']))
    else:
        raise RuntimeError('现有 open_agents 不是数组，停止自动覆盖')
    for keys, value in [(['notify'], current_command), (['tui', 'terminal_title'], title), (['tui', 'keymap', 'global', 'open_agents'], bindings)]:
        before = get_key(doc, keys)
        prior = next((c for c in previous.get('changes', []) if c['keys'] == keys), None) if previous else None
        changes.append({'keys': keys, 'before': prior['before'] if prior else before, 'after': value})
        set_key(doc, keys, value)
    plan = {'action': 'install', 'version': VERSION, 'home': str(args.home), 'notify': current_command,
            'hooks': ['PreToolUse:request_user_input'], 'cleanup': 'VS Code only',
            'legacy_hooks_removed': bool(legacy_script), 'apply': args.apply,
            'dependency_install_allowed': args.install_dependencies}
    if not args.apply:
        return plan
    if sys.platform != 'darwin':
        raise RuntimeError('仅支持本地 macOS 安装；其他平台可使用 --dry-run 检查配置')
    for key in ('codex', 'code'):
        if not env[key]:
            raise RuntimeError('缺少 ' + key + '；请先安装并通过参数指定路径')
    if not env['notifier'] and args.install_dependencies and env['brew']:
        run([env['brew'], 'install', 'terminal-notifier']); env['notifier'] = shutil.which('terminal-notifier')
        if not env['notifier']:
            env['notifier'] = str(Path(run([env['brew'], '--prefix', 'terminal-notifier'])) / 'bin/terminal-notifier')
    if not env['notifier']:
        raise RuntimeError('缺少 terminal-notifier；可通过已有 Homebrew 自动安装')
    vsix = args.vsix or next(iter(sorted((ROOT / 'dist').glob('*.vsix'))), None)
    if not vsix or not Path(vsix).is_file():
        raise RuntimeError('需要 --vsix 指向同版本发布包')
    with zipfile.ZipFile(vsix) as archive:
        package = json.loads(archive.read('extension/package.json'))
        if package['publisher'] + '.' + package['name'] != ID or package['version'] != VERSION:
            raise RuntimeError('VSIX 身份或版本与安装工具不一致')
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    backup = base / 'backups' / stamp; backup.mkdir(parents=True, mode=0o700)
    pointer = Path.home() / '.local/share/codex-focus-notifications/active-home.json'
    tracked = [config_path, hooks_path, runtime_file, manifest_file, script, pointer]
    snapshots = []
    for i, p in enumerate(tracked):
        name = str(i)
        if p.exists():
            shutil.copy2(p, backup / name); os.chmod(backup / name, 0o600)
        snapshots.append({'path': str(p), 'backup': name, 'existed': p.exists(), 'directory': str(backup)})
    installed_extensions = run([env['code'], '--list-extensions', '--show-versions']).splitlines()
    legacy = []
    for item in installed_extensions:
        ext_id, _, ext_version = item.partition('@')
        if ext_id.endswith('.codex-focus-notifications'):
            folder = Path.home() / '.vscode/extensions' / (ext_id + '-' + ext_version)
            if not folder.is_dir():
                raise RuntimeError('无法备份已有扩展，请检查自定义 extensions-dir：' + ext_id)
            archive = backup / (str(len(legacy)) + '.vsix')
            legacy_vsix(folder, archive); legacy.append({'id': ext_id, 'vsix': str(archive)})
    app = Path.home() / 'Applications/Codex Focus Notifications.app'
    if app.exists() and plistlib.loads((app / 'Contents/Info.plist').read_bytes()).get('CFBundleIdentifier') != 'io.github.frequenk.codex-focus-notifications':
        raise RuntimeError('目标 App 目录不是本项目管理的应用，停止覆盖')
    icon = args.icon or ROOT / 'assets/icon.png'
    app_prepared = False
    try:
        notifier = prepare_app(env['notifier'], app, icon)
        app_prepared = True
        for entry in legacy:
            if entry['id'] != ID:
                run([env['code'], '--uninstall-extension', entry['id']])
        run([env['code'], '--install-extension', vsix, '--force'])
        script.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / 'scripts/notify.py', script); os.chmod(script, 0o700)
        private_json(runtime_file, {'version': VERSION, 'python': env['python'], 'codex': env['codex'],
                     'code': env['code'], 'notifier': notifier, 'original_callback': original,
                     'managed_callback': current_command})
        private_json(pointer, {'home': str(args.home)})
        private_json(hooks_path, new_hooks)
        temp = config_path.with_suffix('.install-tmp'); temp.write_text(tk.dumps(doc)); os.chmod(temp, 0o600); temp.replace(config_path)
        private_json(manifest_file, {'version': VERSION, 'changes': changes, 'hook': input_group,
                      'owned_scripts': sorted(owned), 'backup': str(backup),
                      'legacy': previous.get('legacy', legacy) if previous else legacy,
                      'app': str(app), 'hashes': {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in (runtime_file, script)}, 'snapshots': previous.get('snapshots', snapshots) if previous else snapshots})
    except Exception as failure:
        rollback_errors = []
        for item in snapshots:
            p = Path(item['path'])
            if item['existed']:
                shutil.copy2(backup / item['backup'], p)
            else:
                p.unlink(missing_ok=True)
        try: run([env['code'], '--uninstall-extension', ID])
        except Exception as error: rollback_errors.append(str(error))
        for entry in legacy:
            try: run([env['code'], '--install-extension', entry['vsix'], '--force'])
            except Exception as error: rollback_errors.append(str(error))
        old_app = app.with_name(app.name + '.previous')
        if app_prepared:
            if app.exists(): shutil.rmtree(app)
            if old_app.exists(): old_app.rename(app)
        staging = app.with_name(app.name + '.installing')
        if staging.exists(): shutil.rmtree(staging)
        if rollback_errors:
            raise RuntimeError('安装失败，文件已恢复，但部分扩展恢复命令失败；请使用备份：' + str(backup)) from failure
        raise
    plan.update(result='installed', backup=str(backup), next=['重载 VS Code 窗口', '方便时重新启动 Codex TUI', '按 Codex 提示信任新增 hook', '首次通知按 macOS 提示授权'])
    return plan


def uninstall(args, env):
    tk = toml_module(); base = args.home / 'notification-bridge'; manifest_file = base / 'installed.json'
    if not manifest_file.exists():
        return {'action': 'uninstall', 'result': 'not_installed'}
    state = json.loads(manifest_file.read_text())
    for path, digest in state.get('hashes', {}).items():
        if not Path(path).is_file() or hashlib.sha256(Path(path).read_bytes()).hexdigest() != digest:
            return {'action': 'uninstall', 'result': 'conflict', 'conflicts': [path], 'apply': False}
    config = args.home / 'config.toml'; hooks_path = args.home / 'hooks.json'
    doc = tk.parse(config.read_text()); conflicts = []
    for change in state['changes']:
        if get_key(doc, change['keys']) == change['after']:
            set_key(doc, change['keys'], change['before'])
        else:
            conflicts.append('.'.join(change['keys']))
    hooks = json.loads(hooks_path.read_text())
    for groups in hooks.get('hooks', {}).values():
        for group in groups:
            group['hooks'] = [h for h in group.get('hooks', []) if h not in state['hook']['hooks']]
    if conflicts:
        return {'action': 'uninstall', 'result': 'conflict', 'conflicts': conflicts, 'apply': False}
    if not args.apply:
        return {'action': 'uninstall', 'apply': False, 'restore_legacy': args.restore_legacy}
    if not env['code']:
        raise RuntimeError('缺少 VS Code CLI')
    run([env['code'], '--uninstall-extension', ID])
    temp = config.with_suffix('.restore-tmp'); temp.write_text(tk.dumps(doc)); os.chmod(temp, 0o600); temp.replace(config)
    private_json(hooks_path, hooks)
    # 只恢复旧方案自身的 hooks，不覆盖后来添加的用户 hooks。
    snapshots = state['snapshots']
    original_hooks = next((item for item in snapshots if Path(item['path']) == hooks_path), None)
    if original_hooks and original_hooks['existed']:
        source = Path(original_hooks.get('directory', state['backup'])) / original_hooks['backup']
        original_document = json.loads(source.read_text())
        for event, groups in original_document.get('hooks', {}).items():
            for group in groups:
                entries = [h for h in group.get('hooks', []) if owned_hook(h, set(state['owned_scripts']))]
                if not entries: continue
                candidate = dict(group, hooks=entries)
                existing = hooks.setdefault('hooks', {}).setdefault(event, [])
                if not any(all(h in g.get('hooks', []) for h in entries) and g.get('matcher') == candidate.get('matcher') for g in existing):
                    existing.append(candidate)
        private_json(hooks_path, hooks)
    if args.restore_legacy:
        for entry in state['legacy']:
            run([env['code'], '--install-extension', entry['vsix'], '--force'])
    (base / 'runtime.json').unlink(missing_ok=True)
    (args.home / 'scripts/codex-focus-notify.py').unlink(missing_ok=True)
    pointer = Path.home() / '.local/share/codex-focus-notifications/active-home.json'
    if pointer.exists() and json.loads(pointer.read_text()).get('home') == str(args.home):
        pointer.unlink()
    manifest_file.unlink()
    return {'action': 'uninstall', 'result': 'uninstalled', 'backups_preserved': True, 'reload_required': True}


def diagnose(args, env):
    result = dict(env, installed=False, runtime_ready=False)
    runtime_file = args.home / 'notification-bridge/runtime.json'
    manifest = args.home / 'notification-bridge/installed.json'
    if runtime_file.exists():
        runtime = json.loads(runtime_file.read_text())
        result.update(installed=manifest.exists(), installed_version=runtime.get('version'),
                      runtime_ready=(args.home / 'scripts/codex-focus-notify.py').is_file(),
                      notifier_app_ready=Path(runtime.get('notifier', '')).is_file())
        for key in ('python', 'code', 'codex'):
            if runtime.get(key): result[key] = runtime[key]
        try:
            doc = toml_module().parse((args.home / 'config.toml').read_text())
            result['notify_configured'] = get_key(doc, ['notify']) == runtime.get('managed_callback')
            hooks = json.loads((args.home / 'hooks.json').read_text())
            script = str(args.home / 'scripts/codex-focus-notify.py')
            result['question_hook_configured'] = any(owned_hook(h, {script}) and '--input-hook' in h.get('command', '')
                for g in hooks.get('hooks', {}).get('PreToolUse', []) for h in g.get('hooks', []))
        except (OSError, ValueError, RuntimeError) as error:
            result['configuration_error'] = str(error)
    result['missing'] = [key for key in ('codex', 'code') if not result.get(key)]
    if not env.get('notifier') and not result.get('notifier_app_ready'): result['missing'].append('notifier')
    if result.get('codex'):
        try: result['codex_version'] = run([result['codex'], '--version'])
        except Exception: result['codex_version'] = 'unavailable'
    result['activation_note'] = '配置存在不代表已重载窗口、已信任 hook 或已授予系统通知权限'
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['doctor', 'install', 'uninstall'])
    parser.add_argument('--codex-home', type=Path, default=Path(os.environ.get('CODEX_HOME', Path.home() / '.codex')))
    for name in ('codex-bin', 'code-bin', 'notifier-bin'):
        parser.add_argument('--' + name)
    parser.add_argument('--vsix', type=Path); parser.add_argument('--icon', type=Path)
    parser.add_argument('--apply', action='store_true'); parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--install-dependencies', action='store_true'); parser.add_argument('--restore-legacy', action='store_true')
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args(); args.home = args.codex_home.expanduser().resolve()
    if args.dry_run: args.apply = False
    try:
        env = environment(args)
        if args.action == 'doctor':
            result = diagnose(args, env)
        else:
            result = install(args, env) if args.action == 'install' else uninstall(args, env)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if result.get('result') == 'conflict': sys.exit(2)
    except Exception as error:
        print(json.dumps({'result': 'error', 'message': str(error)}, ensure_ascii=False)); sys.exit(1)


if __name__ == '__main__':
    main()
