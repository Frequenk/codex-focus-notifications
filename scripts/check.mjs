import fs from 'node:fs';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
const root = process.cwd();
const skip = new Set(['.git', 'node_modules', '.venv', 'dist', '__pycache__', 'vendor']);
const files = [];
function walk(dir) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (skip.has(entry.name)) continue;
    const file = path.join(dir, entry.name);
    if (entry.isSymbolicLink()) throw Error('公开项目不允许指向本机的符号链接：' + file);
    if (entry.isDirectory()) walk(file); else files.push(file);
  }
}
walk(root);
for (const file of files) {
  if (/\.(?:js|mjs)$/.test(file)) execFileSync(process.execPath, ['--check', file]);
  if (/\.(?:js|mjs|py|json|md|ya?ml|txt)$/.test(file) && !file.endsWith('check.mjs')) {
    const text = fs.readFileSync(file, 'utf8');
    if (/\/Users\/[^/\s]+\/|(?:sk-proj-|afxp_)[A-Za-z0-9_-]{12,}/.test(text)) throw Error('发现个人路径或凭据：' + file);
  }
}
const python = process.env.PYTHON || 'python3';
execFileSync(python, ['-c', 'import ast,sys;[ast.parse(open(p,encoding="utf-8").read(),filename=p) for p in sys.argv[1:]]', ...files.filter(p => p.endsWith('.py'))]);
const pkg = JSON.parse(fs.readFileSync('package.json', 'utf8'));
if (pkg.publisher !== 'frequenk' || pkg.license !== 'MIT') throw Error('公开身份或许可不匹配');
if (process.env.RELEASE_TAG && process.env.RELEASE_TAG !== 'v' + pkg.version) throw Error('标签与 package.json 版本不一致');
console.log('PASS: syntax, public content, identity and release version');
