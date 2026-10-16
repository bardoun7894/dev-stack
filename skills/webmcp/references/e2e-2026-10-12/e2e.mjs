// WebMCP end-to-end proof: raw CDP (WebMCP domain) against headless Chrome, Node 22+ (global WebSocket).
// Usage: node e2e.mjs   (env: CHROME, OUT, DEMO_DIR)
import { spawn, execSync } from 'node:child_process';
import { writeFileSync, statSync, mkdtempSync, rmSync } from 'node:fs';
import { createServer } from 'node:net';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const CHROME = process.env.CHROME || '/root/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome';
const OUT = process.env.OUT || HERE;
const DEMO_DIR = process.env.DEMO_DIR || join(HERE, 'demo');
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const rows = [];
const check = (name, ok, detail = '') => {
  rows.push({ name, ok: !!ok, detail });
  console.log(`[${ok ? 'PASS' : 'FAIL'}] ${name}${detail ? ' :: ' + detail : ''}`);
};
const j = (v) => JSON.stringify(v);

function freePort() {
  return new Promise((res, rej) => {
    const s = createServer();
    s.listen(0, '127.0.0.1', () => { const p = s.address().port; s.close(() => res(p)); });
    s.on('error', rej);
  });
}

async function until(fn, ms, label) {
  const end = Date.now() + ms;
  for (;;) {
    const v = await fn();
    if (v) return v;
    if (Date.now() > end) throw new Error('timeout: ' + label);
    await sleep(100);
  }
}

class Cdp {
  constructor(url) {
    this.ws = new WebSocket(url);
    this.id = 0; this.pending = new Map(); this.events = [];
    this.ws.onmessage = (ev) => {
      const m = JSON.parse(ev.data);
      if (m.id && this.pending.has(m.id)) {
        const { res, rej } = this.pending.get(m.id); this.pending.delete(m.id);
        m.error ? rej(new Error(j(m.error))) : res(m.result);
      } else if (m.method) this.events.push(m);
    };
  }
  open() { return new Promise((res, rej) => { this.ws.onopen = res; this.ws.onerror = rej; }); }
  send(method, params = {}) {
    const id = ++this.id;
    return new Promise((res, rej) => {
      this.pending.set(id, { res, rej });
      this.ws.send(j({ id, method, params }));
      setTimeout(() => this.pending.has(id) && (this.pending.delete(id), rej(new Error('cdp timeout ' + method))), 15000);
    });
  }
  waitEvent(pred, ms, label) { return until(() => this.events.find(pred), ms, label); }
  async evaluate(expression) {
    const r = await this.send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
    if (r.exceptionDetails) throw new Error('eval: ' + j(r.exceptionDetails));
    return r.result.value;
  }
  close() { try { this.ws.close(); } catch {} }
}

const procs = [];
function launch(cmd, args) {
  const p = spawn(cmd, args, { detached: true, stdio: 'ignore' });
  procs.push(p);
  return p;
}
async function stop(p) {
  if (!p || p.exitCode !== null) return;
  try { process.kill(-p.pid, 'SIGTERM'); } catch {} // own process group, by saved PID only
  await Promise.race([new Promise((r) => p.once('exit', r)), sleep(5000)]);
  try { process.kill(-p.pid, 'SIGKILL'); } catch {}
}

async function openPage(flag, httpPort, label) {
  const cdpPort = await freePort();
  const prof = mkdtempSync('/tmp/webmcp-e2e-prof-');
  const args = ['--headless=new', '--no-sandbox', '--disable-gpu', '--window-size=1280,900',
    `--user-data-dir=${prof}`, `--remote-debugging-port=${cdpPort}`];
  if (flag) args.push('--enable-features=WebMCPTesting');
  args.push(`http://127.0.0.1:${httpPort}/index.html`);
  const proc = launch(CHROME, args);
  console.log(`# ${label}: chrome pid=${proc.pid} cdp=${cdpPort} flag=${flag}`);
  const target = await until(async () => {
    try {
      const list = await (await fetch(`http://127.0.0.1:${cdpPort}/json/list`)).json();
      return list.find((t) => t.type === 'page' && t.url.includes(`:${httpPort}`));
    } catch { return null; }
  }, 15000, 'devtools page target');
  const cdp = new Cdp(target.webSocketDebuggerUrl);
  await cdp.open();
  await cdp.send('Runtime.enable');
  await cdp.send('Page.enable');
  return { cdp, proc, prof };
}

const pageText = (sel) => `document.querySelector(${j(sel)})?.innerText ?? null`;
const parseOut = (o) => {
  try {
    const t = typeof o === 'string' ? JSON.parse(o) : o;
    const txt = t?.content?.[0]?.text;
    return txt ? { ...t, parsed: JSON.parse(txt) } : t;
  } catch { return o; }
};

let server;
try {
  // static server
  const httpPort = await freePort();
  server = launch('python3', ['-m', 'http.server', String(httpPort), '--bind', '127.0.0.1', '--directory', DEMO_DIR]);
  console.log(`# http.server pid=${server.pid} port=${httpPort} dir=${DEMO_DIR}`);
  await until(async () => { try { return (await fetch(`http://127.0.0.1:${httpPort}/index.html`)).ok; } catch { return false; } }, 10000, 'http server');

  // ---- run A: WebMCPTesting enabled (skip with ONLY_NEGATIVE=1 to rerun just the control)
  if (!process.env.ONLY_NEGATIVE) {
  const A = await openPage(true, httpPort, 'A (flag on)');
  const { cdp } = A;
  const log = [];
  setInterval(() => {}, 1 << 30).unref();
  const ready = await until(() => cdp.evaluate('window.__toolsReady === true').catch(() => false), 30000, 'page tools ready').catch(() => false);
  const diag = async () => ({
    readyState: await cdp.evaluate('document.readyState').catch((e) => 'err ' + e.message),
    status: await cdp.evaluate(pageText('#webmcp-status')).catch((e) => 'err ' + e.message),
    modelContext: await cdp.evaluate('typeof document.modelContext').catch((e) => 'err ' + e.message),
    url: await cdp.evaluate('location.href').catch((e) => 'err ' + e.message),
    exceptions: cdp.events.filter((e) => e.method === 'Runtime.exceptionThrown').map((e) => e.params.exceptionDetails?.exception?.description || e.params.exceptionDetails?.text),
    console: cdp.events.filter((e) => e.method === 'Runtime.consoleAPICalled').map((e) => e.params.args.map((a) => a.value ?? a.description).join(' ')),
  });
  console.log('# page diagnostics: ' + j(await diag()));
  check('page registered its tools (window.__toolsReady)', ready);
  if (process.env.STOP_AFTER_READY) throw new Error('STOP_AFTER_READY');
  check('flag on: typeof document.modelContext === "object"', (await cdp.evaluate('typeof document.modelContext')) === 'object');

  await cdp.send('WebMCP.enable');
  await until(() => cdp.events.filter((e) => e.method === 'WebMCP.toolsAdded').flatMap((e) => e.params.tools).length >= 3, 8000, 'toolsAdded x3').catch(() => {});
  await sleep(1000);
  const tools = new Map();
  for (const e of cdp.events.filter((e) => e.method === 'WebMCP.toolsAdded')) for (const t of e.params.tools) tools.set(t.name, t);
  console.log('# listed tools (CDP WebMCP.toolsAdded):');
  for (const t of tools.values()) console.log('  ' + j({ name: t.name, description: t.description, annotations: t.annotations, inputSchema: t.inputSchema, frameId: t.frameId, backendNodeId: t.backendNodeId }));
  const names = [...tools.keys()].sort();
  check('WebMCP.enable lists exactly 3 tools', j(names) === j(['add_to_cart', 'contact_form', 'search_courses']), j(names));
  check('annotation map: search_courses readOnly=true', tools.get('search_courses')?.annotations?.readOnly === true, j(tools.get('search_courses')?.annotations));
  check('annotation map: add_to_cart consequential=true', tools.get('add_to_cart')?.annotations?.consequential === true, j(tools.get('add_to_cart')?.annotations));
  check('contact_form is declarative (has backendNodeId)', typeof tools.get('contact_form')?.backendNodeId === 'number', String(tools.get('contact_form')?.backendNodeId));

  async function invoke(name, input, waitMs = 10000) {
    const t = tools.get(name);
    const r = await cdp.send('WebMCP.invokeTool', { frameId: t.frameId, toolName: name, input });
    console.log(`# invokeTool ${name} ${j(input)} -> invocationId=${r.invocationId}`);
    const ev = await cdp.waitEvent((e) => e.method === 'WebMCP.toolResponded' && e.params.invocationId === r.invocationId, waitMs, `toolResponded ${name}`);
    return ev.params;
  }
  const show = (p) => console.log('  response: ' + j({ status: p.status, output: parseOut(p.output), errorText: p.errorText, exception: p.exception?.description }));

  // search_courses
  try {
    const r = await invoke('search_courses', { query: 'IELTS' });
    show(r);
    const out = parseOut(r.output);
    const dom = await cdp.evaluate(pageText('#results'));
    console.log('  DOM #results: ' + j(dom));
    check('search_courses invoked, status Completed, 2 IELTS courses returned', r.status === 'Completed' && out?.parsed?.count === 2, `status=${r.status} count=${out?.parsed?.count}`);
    check('page reacted: #results shows both IELTS courses', /c101/.test(dom) && /c102/.test(dom) && !/Python/.test(dom), j(dom));
  } catch (e) { check('search_courses', false, e.message); }

  // add_to_cart
  try {
    const before = await cdp.evaluate(pageText('#cart-count'));
    const r = await invoke('add_to_cart', { courseId: 'c101' });
    show(r);
    const out = parseOut(r.output);
    const dom = await cdp.evaluate(pageText('#cart'));
    const count = await cdp.evaluate(pageText('#cart-count'));
    console.log(`  DOM cart-count: ${before} -> ${count}; #cart: ${j(dom)}`);
    check('add_to_cart invoked, status Completed, cart=[c101]', r.status === 'Completed' && j(out?.parsed?.cart) === '["c101"]', `status=${r.status}`);
    check('page reacted: #cart lists c101, count 0 -> 1', /c101/.test(dom) && before === '0' && count === '1', `${before}->${count}`);
  } catch (e) { check('add_to_cart', false, e.message); }

  // contact_form (declarative)
  try {
    const input = { name: 'Sara Ali', email: 'sara@example.com', message: 'Which IELTS course fits band 6?' };
    const t = tools.get('contact_form');
    const r0 = await cdp.send('WebMCP.invokeTool', { frameId: t.frameId, toolName: 'contact_form', input });
    console.log(`# invokeTool contact_form ${j(input)} -> invocationId=${r0.invocationId}`);
    let ev = await cdp.waitEvent((e) => e.method === 'WebMCP.toolResponded' && e.params.invocationId === r0.invocationId, 6000, 'contact_form autosubmit').catch(() => null);
    let path = 'autosubmit (toolautosubmit): toolResponded arrived without a user submit';
    if (!ev) {
      const filled = await cdp.evaluate(`Object.fromEntries(new FormData(document.querySelector('#contact')))`);
      console.log('  no response in 6 s; form fields as filled by the agent: ' + j(filled));
      await cdp.evaluate(`document.querySelector('#contact').requestSubmit()`);
      path = 'fallback: fields filled by agent, form.requestSubmit() needed';
      ev = await cdp.waitEvent((e) => e.method === 'WebMCP.toolResponded' && e.params.invocationId === r0.invocationId, 6000, 'contact_form after requestSubmit').catch(() => null);
    }
    const dom = await cdp.evaluate(pageText('#contact-status'));
    const fields = await cdp.evaluate(`Object.fromEntries(new FormData(document.querySelector('#contact')))`);
    console.log('  path: ' + path);
    if (ev) show(ev.params);
    console.log('  DOM #contact-status: ' + j(dom) + '; form fields: ' + j(fields));
    check('contact_form invoked via CDP, status Completed', ev?.params.status === 'Completed', `path=${path}; status=${ev?.params.status}`);
    check('page reacted: form filled and #contact-status shows sender', fields.name === 'Sara Ali' && fields.email === 'sara@example.com' && /Sara Ali/.test(dom || ''), j(dom));
  } catch (e) { check('contact_form', false, e.message); }

  // negative tool call: unknown course id must be rejected by the page
  try {
    const r = await invoke('add_to_cart', { courseId: 'nope' });
    const out = parseOut(r.output);
    console.log('  bad input -> ' + j({ status: r.status, out }));
    const count = await cdp.evaluate(pageText('#cart-count'));
    check('untrusted input: unknown courseId rejected, cart unchanged', count === '1' && (out?.isError === true || r.status !== 'Completed'), `count=${count} isError=${out?.isError}`);
  } catch (e) { check('untrusted input rejected', false, e.message); }

  // screenshot
  const shot = await cdp.send('Page.captureScreenshot', { format: 'png' });
  const shotPath = join(OUT, 'after.png');
  writeFileSync(shotPath, Buffer.from(shot.data, 'base64'));
  check('screenshot after.png written', statSync(shotPath).size > 0, `${statSync(shotPath).size} bytes`);

  const errs = cdp.events.filter((e) => e.method === 'Runtime.exceptionThrown');
  console.log('# page exceptions: ' + errs.length);
  cdp.close();
  await stop(A.proc);
  rmSync(A.prof, { recursive: true, force: true });

  }

  // ---- run B: flag off (negative control)
  const B = await openPage(false, httpPort, 'B (flag off)');
  // the target URL is listed before navigation commits; wait for the real page's script to have run
  await until(() => B.cdp.evaluate(`document.readyState === 'complete' && document.querySelector('#q') !== null && document.getElementById('webmcp-status')?.textContent.startsWith('unavailable') === true`).catch(() => false), 30000, 'page B load');
  check('flag off: typeof document.modelContext === "undefined"', (await B.cdp.evaluate('typeof document.modelContext')) === 'undefined');
  console.log('  #webmcp-status: ' + j(await B.cdp.evaluate(pageText('#webmcp-status'))));
  await B.cdp.evaluate(`document.querySelector('#q').value='Python'; document.querySelector('#manual-search').click();`);
  const manual = await B.cdp.evaluate(pageText('#results'));
  check('flag off: page still works through its normal UI', /c301/.test(manual || ''), j(manual));
  B.cdp.close();
  await stop(B.proc);
  rmSync(B.prof, { recursive: true, force: true });
} catch (e) {
  check('run completed without exception', false, e.stack || e.message);
} finally {
  for (const p of procs) await stop(p);
  await sleep(500);
  const left = execSync('ps -eo pid,args').toString().split('\n').filter((l) => (l.includes('webmcp-e2e-prof') || l.includes('--directory ' + DEMO_DIR)) && !/ps -eo/.test(l) && !l.includes(String(process.pid)));
  check('cleanup: no leftover chrome/http.server processes', left.length === 0, left.join(' | '));
  console.log('\n| Check | Result | Detail |\n|---|---|---|');
  for (const r of rows) console.log(`| ${r.name} | ${r.ok ? 'PASS' : 'FAIL'} | ${r.detail.replace(/\|/g, '/').slice(0, 140)} |`);
  const failed = rows.filter((r) => !r.ok).length;
  console.log(`\n${rows.length - failed}/${rows.length} passed`);
  process.exit(failed ? 1 : 0);
}
