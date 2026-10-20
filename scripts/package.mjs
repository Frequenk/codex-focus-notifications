import fs from 'node:fs';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
const pkg = JSON.parse(fs.readFileSync('package.json', 'utf8'));
fs.mkdirSync('dist', { recursive: true });
execFileSync(process.execPath, [path.resolve('node_modules/@vscode/vsce/vsce'), 'package', '--no-dependencies',
  '--out', path.join('dist', `${pkg.name}-${pkg.version}.vsix`)], { stdio: 'inherit' });
