// node --test tests/jev_browse_ready.test.mjs — jev-browse waits for a slow page before judging it (real Chrome,
// local server, no Jev call: --observe prints what Jev would be offered, and decides nothing).
import test from 'node:test';
import assert from 'node:assert/strict';
import { execFile } from 'node:child_process';
import { createServer } from 'node:http';
import { existsSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const SCRIPT = join(ROOT, 'skills', 'jev', 'scripts', 'jev-browse.mjs');
const CHROME = process.env.JEV_BROWSER || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';

// A KPI card that shows "-" until the data arrives. The data endpoint answers after 3 s, like a slow backend.
// mode=inflight: the fetch starts on load, so a request is in flight the whole time.
// mode=timer:    nothing is in flight for the first 3 s; the fetch is only started by a timer.
const KPI_PAGE = (mode) => `<!doctype html><title>KPI</title><h1>Dashboard</h1>
<div id="kpi">-</div><button>Refresh</button>
<script>
const show = (d) => { document.getElementById('kpi').textContent = d.label; };
const load = () => fetch('/kpi').then((r) => r.json()).then(show);
${mode === 'timer' ? 'setTimeout(load, 3000);' : 'load();'}
</script>`;

// A page that never goes quiet: the text changes every 100 ms. The cap has to end the wait, without an error.
const CLOCK_PAGE = `<!doctype html><title>Clock</title><h1>Live</h1><div id="t">0</div><button>Pause</button>
<script>setInterval(() => { document.getElementById('t').textContent = String(Date.now()); }, 100);</script>`;

let server;
let base;
test.before(async () => {
  server = createServer((req, res) => {
    const url = new URL(req.url, 'http://x');
    if (url.pathname === '/kpi') {
      setTimeout(() => { res.setHeader('content-type', 'application/json'); res.end('{"label":"Sales 1,234"}'); }, 3000);
    } else if (url.pathname === '/clock') {
      res.setHeader('content-type', 'text/html'); res.end(CLOCK_PAGE);
    } else {
      res.setHeader('content-type', 'text/html'); res.end(KPI_PAGE(url.searchParams.get('mode')));
    }
  });
  await new Promise((r) => server.listen(0, '127.0.0.1', r));
  base = `http://127.0.0.1:${server.address().port}`;
});
test.after(() => server.close());

const skip = !existsSync(CHROME) && !process.env.JEV_BROWSER && 'no Google Chrome found';

// Runs --observe and returns the page text Jev would be offered.
function observe(extra, timeout = 60000) {
  return new Promise((resolve, reject) => {
    const started = Date.now();
    execFile(process.execPath, [SCRIPT, '--goal', 'read the dashboard', '--observe', ...extra],
      { env: { ...process.env, JEV_BROWSER: CHROME }, timeout },
      (err, stdout, stderr) => {
        if (err) return reject(new Error(`${err.message}\n${stderr}`));
        resolve({ state: JSON.parse(stdout).state, seconds: (Date.now() - started) / 1000 });
      });
  });
}

test('a fetch still in flight on load is waited for: the filled value is what Jev sees', { skip }, async () => {
  const { state } = await observe(['--url', `${base}/?mode=inflight`]);
  assert.match(state.page, /Sales 1,234/);
});

test('--wait-for: a value that only appears after a timer and a fetch is waited for', { skip }, async () => {
  const { state } = await observe(['--url', `${base}/?mode=timer`, '--wait-for', 'Sales 1,234']);
  assert.match(state.page, /Sales 1,234/);
});

test('a page that never goes quiet is capped by --ready-timeout, without an error', { skip }, async () => {
  const { state, seconds } = await observe(['--url', `${base}/clock`, '--ready-timeout', '1500']);
  assert.match(state.page, /Live/);
  assert.ok(seconds < 8, `took ${seconds}s, the cap should have ended the wait`);
});
