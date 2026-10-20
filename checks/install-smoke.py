#!/usr/bin/env python3
"""在临时 HOME 中验收安装、迁移、重复安装、冲突与恢复整条流程。"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import plistlib
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('manage', ROOT / 'scripts/manage.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
with tempfile.TemporaryDirectory(prefix='codex-install-smoke-') as temporary:
    root = Path(temporary); old_home = os.environ.get('HOME'); old_platform = sys.platform
    os.environ['HOME'] = str(root); sys.platform = 'darwin'
    try:
        home = root / 'codex'; home.mkdir()
        legacy_script = root / 'old-notify.py'
        legacy_script.write_text("ORIGINAL_CALLBACK = ['echo', 'prior-callback']\ndef is_session_foreground(): pass\ndef handle_clear_hook(): pass\n")
        original_notify = [sys.executable, str(legacy_script)]
        (home / 'config.toml').write_text('# 保留用户注释\nnotify = ' + json.dumps(original_notify) + '\nmodel = "fixture-model"\n[tui.keymap.global]\nopen_agents = ["f10"]\n')
        def hook(flag): return {'type': 'command', 'command': 'python3 ' + str(legacy_script) + ' ' + flag, 'timeout': 3}
        old_hooks = {event: [{'hooks': [hook('--clear-hook')]}] for event in ('PostToolUse', 'UserPromptSubmit', 'SessionStart', 'SessionEnd')}
        user_hook = {'type': 'command', 'command': 'echo keep-user-hook'}
        old_hooks['PreToolUse'] = [{'matcher': 'Read', 'hooks': [user_hook]}, {'matcher': '^request_user_input$', 'hooks': [hook('--input-hook')]}]
        (home / 'hooks.json').write_text(json.dumps({'hooks': old_hooks}))
        package = json.loads((ROOT / 'package.json').read_text())
        archive = root / 'new.vsix'
        with zipfile.ZipFile(archive, 'w') as z: z.writestr('extension/package.json', json.dumps(package))
        old_id = 'legacy.codex-focus-notifications'
        folder = root / '.vscode/extensions' / (old_id + '-0.2.0'); folder.mkdir(parents=True)
        old_package = dict(package, publisher='legacy', version='0.2.0')
        (folder / 'package.json').write_text(json.dumps(old_package)); (folder / 'extension.js').write_text('module.exports = {};')
        installed = {old_id: '0.2.0'}
        def external(argv):
            args = [str(x) for x in argv]
            if '--list-extensions' in args:
                return '\n'.join(key + '@' + value for key, value in installed.items())
            if '--uninstall-extension' in args:
                installed.pop(args[-1], None); return ''
            if '--install-extension' in args:
                p = Path(args[args.index('--install-extension') + 1])
                with zipfile.ZipFile(p) as z: metadata = json.loads(z.read('extension/package.json'))
                name = metadata['publisher'] + '.' + metadata['name']; installed[name] = metadata['version']
                dest = root / '.vscode/extensions' / (name + '-' + metadata['version']); dest.mkdir(parents=True, exist_ok=True)
                (dest / 'package.json').write_text(json.dumps(metadata)); (dest / 'extension.js').write_text('module.exports = {};')
                return ''
            raise AssertionError('意外外部命令：' + repr(args))
        def notification_app(binary, target, icon):
            (target / 'Contents').mkdir(parents=True, exist_ok=True)
            (target / 'Contents/Info.plist').write_bytes(plistlib.dumps({'CFBundleIdentifier': 'io.github.frequenk.codex-focus-notifications'}))
            return str(root / 'mock-notifier')
        m.run = external; m.prepare_app = notification_app
        args = argparse.Namespace(home=home, apply=False, install_dependencies=False, vsix=archive, icon=None, restore_legacy=False)
        env = {'python': sys.executable, 'code': 'mock-code', 'codex': 'mock-codex', 'notifier': 'mock-notifier', 'brew': None}
        before = {p.name: p.read_bytes() for p in home.iterdir()}
        assert m.install(args, env)['apply'] is False
        assert before == {p.name: p.read_bytes() for p in home.iterdir()}, '预览修改了配置'
        args.apply = True; m.install(args, env)
        assert installed == {m.ID: m.VERSION}
        doc = m.toml_module().parse((home / 'config.toml').read_text())
        assert doc['model'] == 'fixture-model' and '# 保留用户注释' in (home / 'config.toml').read_text()
        assert list(doc['tui']['keymap']['global']['open_agents']) == ['f10', 'f12']
        runtime = json.loads((home / 'notification-bridge/runtime.json').read_text())
        assert runtime['original_callback'] == ['echo', 'prior-callback']
        hooks = json.loads((home / 'hooks.json').read_text())['hooks']
        assert all(not hooks[event] for event in ('PostToolUse', 'UserPromptSubmit', 'SessionStart', 'SessionEnd'))
        assert sum(len(g['hooks']) for g in hooks['PreToolUse']) == 2
        m.install(args, env)
        hooks = json.loads((home / 'hooks.json').read_text())
        assert sum(len(g['hooks']) for g in hooks['hooks']['PreToolUse']) == 2, '重复安装增加了 hook'
        hooks['hooks']['SessionEnd'].append({'hooks': [{'type': 'command', 'command': 'echo added-after-install'}]})
        m.private_json(home / 'hooks.json', hooks)
        doc = m.toml_module().parse((home / 'config.toml').read_text())
        doc['model'] = 'user-new-model'; doc['notify'] = ['echo', 'user-custom-notify']
        (home / 'config.toml').write_text(m.toml_module().dumps(doc))
        assert m.uninstall(args, env)['result'] == 'conflict'
        doc['notify'] = runtime['managed_callback']; (home / 'config.toml').write_text(m.toml_module().dumps(doc))
        args.restore_legacy = True
        assert m.uninstall(args, env)['result'] == 'uninstalled'
        doc = m.toml_module().parse((home / 'config.toml').read_text())
        assert doc['model'] == 'user-new-model' and list(doc['notify']) == original_notify
        assert list(doc['tui']['keymap']['global']['open_agents']) == ['f10']
        hooks = json.loads((home / 'hooks.json').read_text())['hooks']
        assert any(h['command'] == 'echo added-after-install' for g in hooks['SessionEnd'] for h in g['hooks'])
        assert any('--clear-hook' in h['command'] for g in hooks['SessionEnd'] for h in g['hooks'])
        assert installed == {old_id: '0.2.0'}
        print('PASS: dry run, full install, legacy migration, idempotency, user callback/hooks, conflict guard, incremental restore')
    finally:
        sys.platform = old_platform
        if old_home is None: os.environ.pop('HOME', None)
        else: os.environ['HOME'] = old_home
