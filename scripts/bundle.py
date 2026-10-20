#!/usr/bin/env python3
"""构建供 agent 安装的同版本工具包，并生成发布校验和。"""
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
version = json.loads((ROOT / 'package.json').read_text())['version']
dist = ROOT / 'dist'; dist.mkdir(exist_ok=True)
vsix = dist / ('codex-focus-notifications-' + version + '.vsix')
if not vsix.exists():
    raise SystemExit('请先运行 npm run package')
name = 'codex-focus-notifications-' + version + '-agent'
with tempfile.TemporaryDirectory() as tmp:
    staging = Path(tmp) / name; staging.mkdir()
    for file in ('package.json', 'LICENSE', 'THIRD_PARTY_NOTICES.md', 'README.md', 'INSTALL.md', 'requirements-build.txt'):
        shutil.copy2(ROOT / file, staging / file)
    for directory in ('assets', 'scripts'):
        (staging / directory).mkdir()
    for file in ('manage.py', 'notify.py'):
        shutil.copy2(ROOT / 'scripts' / file, staging / 'scripts' / file)
    shutil.copy2(ROOT / 'assets/icon.png', staging / 'assets/icon.png')
    subprocess.run([sys.executable, '-m', 'pip', 'install', '--disable-pip-version-check', '--require-hashes',
                    '--only-binary=:all:', '--no-deps', '--target', str(staging / 'vendor'),
                    '-r', str(ROOT / 'requirements-build.txt')], check=True)
    for cache in (staging / 'vendor').rglob('__pycache__'):
        shutil.rmtree(cache)
    target = dist / (name + '.tar.gz')
    with target.open('wb') as stream, gzip.GzipFile(fileobj=stream, mode='wb', filename='', mtime=0) as compressed:
        with tarfile.open(fileobj=compressed, mode='w') as archive:
            for file in sorted(staging.rglob('*')):
                if not file.is_file(): continue
                info = archive.gettarinfo(str(file), arcname=name + '/' + str(file.relative_to(staging)))
                info.uid = info.gid = info.mtime = 0; info.uname = info.gname = ''
                with file.open('rb') as content:
                    archive.addfile(info, content)
(dist / 'SHA256SUMS').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest() + '  ' + p.name + '\n' for p in (vsix, target)))
print(target.name)
