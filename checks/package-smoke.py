#!/usr/bin/env python3
"""检查发布内容、校验和，并从解压工具包执行真实安装预览。"""
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tarfile
import tempfile
import zipfile

root = Path(__file__).resolve().parents[1]
version = json.loads((root / 'package.json').read_text())['version']; dist = root / 'dist'
for line in (dist / 'SHA256SUMS').read_text().splitlines():
    digest, name = line.split('  ', 1)
    assert hashlib.sha256((dist / name).read_bytes()).hexdigest() == digest
with zipfile.ZipFile(dist / ('codex-focus-notifications-' + version + '.vsix')) as z:
    files = z.namelist(); package = json.loads(z.read('extension/package.json'))
    assert package['publisher'] == 'frequenk' and package['version'] == version
    for name in ('src/extension.js', 'src/click.js', 'src/jump.js', 'src/screen.js', 'src/server.js', 'scripts/notify.py', 'assets/icon.png', 'LICENSE.txt'):
        assert 'extension/' + name in files, name
    assert not any('/backups/' in name or '/node_modules/' in name or name.endswith('.sqlite') for name in files)
with tempfile.TemporaryDirectory(prefix='codex-package-smoke-') as tmp:
    temp = Path(tmp)
    with tarfile.open(dist / ('codex-focus-notifications-' + version + '-agent.tar.gz')) as archive:
        for member in archive.getmembers():
            p = PurePosixPath(member.name)
            assert not p.is_absolute() and '..' not in p.parts and member.isfile(), member.name
        for member in archive.getmembers():
            target = temp / member.name; target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.extractfile(member).read())
    toolkit = next(temp.iterdir())
    assert any(p.name.lower().startswith('license') for p in (toolkit / 'vendor').rglob('*'))
    home = temp / 'empty-home'
    result = subprocess.check_output([sys.executable, str(toolkit / 'scripts/manage.py'), 'install', '--codex-home', str(home), '--dry-run', '--json'], text=True)
    assert json.loads(result)['apply'] is False and not home.exists()
print('PASS: VSIX identity/payload, checksums, toolkit license, safe archive and offline installation preview')
