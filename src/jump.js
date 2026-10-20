'use strict';
const { Screen } = require('./screen');
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
async function jump(options) {
  const screen = new Screen(); options.capture(screen);
  const send = data => { if (!options.alive()) throw new Error('terminal_or_focus_changed'); options.send(data); };
  const end = Date.now() + 10000;
  const center = lines => lines.slice(0, 8).some(line => /^\s*Agent command center\b/.test(line));
  const searchRow = lines => lines.findIndex(line => line.includes('Search › '));
  const query = line => line.split('Search › ')[1]?.split('│')[0].trim();
  const editing = lines => screen.cursorVisible && screen.y === searchRow(lines);
  async function wait(stage, predicate, titleOnly = false) {
    options.stage(stage);
    const deadline = titleOnly ? end : Math.min(end, Date.now() + 3500);
    let since = 0;
    while (Date.now() < deadline) {
      if (!options.alive()) throw new Error('terminal_or_focus_changed');
      const lines = screen.lines();
      if ((titleOnly || !screen.frame) && predicate(lines, screen.text())) {
        if (!since) since = Date.now();
        if (Date.now() - since >= (stage === 'verify_selection' ? 450 : 100)) return;
      } else since = 0;
      await sleep(25);
    }
    throw new Error('timeout_' + stage);
  }
  try {
    send('\x1b[24~');
    await wait('agents', (lines, text) => center(lines) && /\bGroup:/.test(text));
    if (editing(screen.lines())) {
      send('\x1bOR');
      await wait('reset_search', lines => center(lines) && !editing(lines));
    }
    send('\x1bOR');
    await wait('search', lines => center(lines) && editing(lines));
    const line = screen.lines()[searchRow(screen.lines())];
    if (!line || query(line)) throw new Error('search_not_empty');
    send('\x1b[200~' + options.identity.name + '\x1b[201~');
    await wait('verify_selection', (lines, text) => {
      if (!center(lines)) return false;
      const row = searchRow(lines);
      if (row < 0 || query(lines[row]) !== options.identity.name) return false;
      return lines.some((item, index) => {
        const column = item.indexOf('Task details');
        if (column < 0) return false;
        return lines.slice(index + 1, index + 5).some(next => next.split('│')[1]?.trim() === options.identity.name);
      }) && /Task details/.test(text);
    });
    send('\r');
    await wait('title', () => options.currentId() === options.threadId, true);
    return { result: 'opened', thread_id: options.threadId };
  } finally { options.capture(null); }
}
module.exports = { jump };
