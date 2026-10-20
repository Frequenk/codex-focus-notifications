import fs from 'node:fs';
import path from 'node:path';

// 只在 CI 工作目录中写入构建版本，不产生版本提交。
const args = process.argv.slice(2);
const option = name => { const i = args.indexOf(name); return i < 0 ? undefined : args[i + 1]; };
const directory = path.resolve(option('--directory') || '.');
const pkgFile = path.join(directory, 'package.json');
const lockFile = path.join(directory, 'package-lock.json');
const pkg = JSON.parse(fs.readFileSync(pkgFile, 'utf8'));
const parse = text => {
  const match = /^v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$/.exec(text || '');
  if (!match) return null;
  const values = match.slice(1).map(Number);
  if (!values.every(Number.isSafeInteger)) throw Error('版本号超过安全整数范围');
  return values;
};
const compare = (a, b) => a[0] - b[0] || a[1] - b[1] || a[2] - b[2];
const base = parse(pkg.version);
if (!base) throw Error('自动发布需要 package.json 使用稳定的 major.minor.patch 版本');
async function list(endpoint) {
  const repo = process.env.GITHUB_REPOSITORY;
  if (!/^[\w.-]+\/[\w.-]+$/.test(repo || '')) throw Error('缺少有效的 GITHUB_REPOSITORY');
  const result = [];
  for (let page = 1; page <= 100; page++) {
    const headers = { Accept: 'application/vnd.github+json', 'User-Agent': 'codex-focus-notifications-release' };
    if (process.env.GH_TOKEN) headers.Authorization = `Bearer ${process.env.GH_TOKEN}`;
    const response = await fetch(`https://api.github.com/repos/${repo}/${endpoint}?per_page=100&page=${page}`,
      { headers, signal: AbortSignal.timeout(20000) });
    if (!response.ok) throw Error(`读取 GitHub ${endpoint} 失败：HTTP ${response.status}`);
    const values = await response.json();
    if (!Array.isArray(values)) throw Error('GitHub 返回了无效列表');
    result.push(...values);
    if (values.length < 100) return result;
  }
  throw Error('GitHub 分页未完整读取，停止分配版本');
}
const snapshot = option('--snapshot');
const data = snapshot ? JSON.parse(fs.readFileSync(snapshot, 'utf8'))
  : { releases: await list('releases'), tags: await list('tags') };
if (!Array.isArray(data.releases) || !Array.isArray(data.tags)) throw Error('发布快照格式无效');
const sha = process.env.GITHUB_SHA;
const existing = sha && data.releases.find(item => !item.draft && !item.prerelease
  && item.target_commitish === sha && parse(item.tag_name));
let version;
if (existing) {
  version = parse(existing.tag_name).join('.');
} else {
  const used = [...data.releases.map(item => item.tag_name), ...data.tags.map(item => item.name)]
    .map(parse).filter(Boolean).sort(compare);
  let next = [...base];
  if (used.length && compare(used.at(-1), base) >= 0) {
    next = [...used.at(-1)]; next[2]++;
    if (!Number.isSafeInteger(next[2])) throw Error('补丁版本超过安全整数范围');
  }
  version = next.join('.');
}
const result = { version, tag: 'v' + version, already_published: Boolean(existing) };
if (args.includes('--apply')) {
  const lock = JSON.parse(fs.readFileSync(lockFile, 'utf8'));
  pkg.version = version; lock.version = version;
  if (!lock.packages?.['']) throw Error('锁文件缺少根包信息');
  lock.packages[''].version = version;
  fs.writeFileSync(pkgFile, JSON.stringify(pkg, null, 2) + '\n');
  fs.writeFileSync(lockFile, JSON.stringify(lock, null, 2) + '\n');
}
if (process.env.GITHUB_OUTPUT) {
  fs.appendFileSync(process.env.GITHUB_OUTPUT, Object.entries(result).map(([k, v]) => `${k}=${v}\n`).join(''));
}
console.log(JSON.stringify(result));
