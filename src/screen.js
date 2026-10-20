'use strict';
class Screen {
  constructor() { this.rows = new Map(); this.x = 0; this.y = 0; this.pending = ''; this.frame = false; this.cursorVisible = false; }
  clear() { this.rows.clear(); }
  feed(chunk) {
    const data = this.pending + chunk;
    this.pending = '';
    for (let i = 0; i < data.length;) {
      const c = data[i];
      if (c === '\x1b') {
        if (i + 1 >= data.length) { this.pending = data.slice(i); break; }
        const rest = data.slice(i);
        if (rest.startsWith('\x1b[')) {
          const m = rest.match(/^\x1b\[([0-?]*)([ -/]*)([@-~])/);
          if (!m) { if (rest.length < 4096) this.pending = rest; break; }
          this.csi(m[1], m[3]); i += m[0].length; continue;
        }
        if (rest.startsWith('\x1b]') || rest.startsWith('\x1bP')) {
          const end = rest.search(/\x07|\x1b\\/);
          if (end < 0) { if (rest.length < 4096) this.pending = rest; break; }
          i += end + (rest[end] === '\x07' ? 1 : 2); continue;
        }
        if (rest[1] === '7') this.saved = [this.x, this.y];
        if (rest[1] === '8' && this.saved) [this.x, this.y] = this.saved;
        i += 2; continue;
      }
      if (c === '\r') this.x = 0;
      else if (c === '\n') this.y = Math.min(255, this.y + 1);
      else if (c === '\b') this.x = Math.max(0, this.x - 1);
      else if (c === '\t') this.x = Math.min(511, (Math.floor(this.x / 8) + 1) * 8);
      else if (c >= ' ' && c !== '\x7f') {
        const cp = data.codePointAt(i); const text = String.fromCodePoint(cp);
        if (!/\p{Mark}/u.test(text) && cp !== 0xfe0f) {
          const width = cp >= 0x1100 && (cp <= 0x115f || cp >= 0x2e80 && cp <= 0xa4cf
            || cp >= 0xac00 && cp <= 0xd7ff || cp >= 0xf900 && cp <= 0xfaff
            || cp >= 0xfe10 && cp <= 0xfe6f || cp >= 0xff01 && cp <= 0xff60 || cp >= 0x1f300) ? 2 : 1;
          const row = this.rows.get(this.y) || [];
          row[this.x] = text;
          if (width === 2) row[this.x + 1] = '';
          this.rows.set(this.y, row); this.x = Math.min(511, this.x + width);
        }
        i += text.length; continue;
      }
      i++;
    }
  }
  csi(params, action) {
    if (params.startsWith('?')) {
      if (params === '?2026') this.frame = action === 'h';
      if (params === '?25') this.cursorVisible = action === 'h';
      if (params === '?1049' && action === 'h') { this.clear(); this.x = this.y = 0; }
      return;
    }
    const p = params.split(';').map(n => Number(n) || 0); const n = p[0] || 1;
    if (action === 'H' || action === 'f') { this.y = Math.min(255, n - 1); this.x = Math.min(511, (p[1] || 1) - 1); }
    else if (action === 'A') this.y = Math.max(0, this.y - n);
    else if (action === 'B') this.y = Math.min(255, this.y + n);
    else if (action === 'C') this.x = Math.min(511, this.x + n);
    else if (action === 'D') this.x = Math.max(0, this.x - n);
    else if (action === 'G') this.x = Math.min(511, n - 1);
    else if (action === 'd') this.y = Math.min(255, n - 1);
    else if (action === 'E' || action === 'F') { this.y = Math.max(0, Math.min(255, this.y + (action === 'E' ? n : -n))); this.x = 0; }
    else if (action === 'J') {
      if (p[0] === 2 || p[0] === 3) this.clear();
      else { for (const y of this.rows.keys()) if (p[0] === 1 ? y < this.y : y > this.y) this.rows.delete(y); this.eraseLine(p[0]); }
    } else if (action === 'K') this.eraseLine(p[0]);
    else if (action === 's') this.saved = [this.x, this.y];
    else if (action === 'u' && this.saved) [this.x, this.y] = this.saved;
  }
  eraseLine(mode) {
    if (mode === 2) { this.rows.delete(this.y); return; }
    const row = this.rows.get(this.y) || [];
    if (mode === 1) { for (let x = 0; x <= this.x; x++) row[x] = ' '; }
    else row.splice(this.x);
    this.rows.set(this.y, row);
  }
  lines() {
    const max = Math.max(0, ...this.rows.keys());
    return Array.from({ length: max + 1 }, (_, y) => {
      const row = this.rows.get(y) || [];
      return Array.from({ length: row.length }, (_, x) => row[x] === undefined ? ' ' : row[x]).join('').trimEnd();
    });
  }
  text() { return this.lines().join('\n'); }
}

module.exports = { Screen };
