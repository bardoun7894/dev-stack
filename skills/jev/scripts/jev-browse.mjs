#!/usr/bin/env node
// jev-browse — System 1 browser agent: Jev picks every operation and target, an LLM only sees the failures.
//
//   jev-browse --url URL --goal "log in" --expect "dashboard shows today sales" [--data '{"email":"a@b.co"}']
//   jev-browse --flows flows.json        [{name, url, goal, expect, data}], run in parallel
//   jev-browse --url URL --goal … --adversarial N   N parallel sessions over the personas
//              (normal, invalid_input, hostile_input, double_submit, back_button); reports only broken ones
//   jev-browse --login --profile tokyo --url https://dash.example/login   sign in ONCE by hand; every later
//              `--profile tokyo` run reuses that session, so flows can test pages behind auth
//
//   options: --max-steps 15 --json
//            --profile NAME   run in a persistent Chrome profile of its own (~/.cache/jev-browse/profiles),
//                             carrying whatever you signed into with --login. Never your everyday profile:
//                             Chrome 136+ refuses remote debugging there, and a test run has no business
//                             acting inside a live browsing session
//            --cdp URL        drive an already-running browser instead of launching Chrome (e.g. Lightpanda
//                             at http://127.0.0.1:9222); it reports no layout, so scrolling, occlusion and
//                             visibility checks degrade to DOM-only there
//            --allow-submit   let a flow without --data press form buttons and change dropdowns (off by default)
//            --autofill       let a small LLM write values for fields --data does not cover (never passwords)
//            --dom-input      drive the DOM (element.click / value setter) even where real input is available
//            --headful        real, visible Chrome window: flows run one at a time, slowed down, and each element
//                             is outlined before Jev acts on it, so you can watch
//            --chrome         force the bundled headless Chrome even when --cdp is set
//            --screenshots D  save D/<flow>/NN.png per step plus final.png and final-full.png (implies --chrome);
//                             Jev is text-only, so layout/visual checks are a vision model reading these (L3)
//
// One Jev request per step carries the operation question AND one target head per operation, so choosing
// "which operation" and "which element" costs a single round trip (speculative fan-out, from
// browser-use/jev-ultrafast). Observation is one atomic evaluate; node identity is a WeakMap on the page, so
// nothing is written to the DOM under test and a re-render is detected instead of silently mis-clicked.
// Every target is re-validated (identity, visibility, viewport, occlusion) in the same evaluate that acts on
// it; a stale decision re-observes rather than executing.
//
// Read-only by default: without --data or --allow-submit it never presses a button inside a form, never
// changes a dropdown, and never follows a link off the site under test (those are listed as external_links).
//
// A browser reached over --cdp may not lay pages out (Lightpanda does not); geometry-based filtering,
// scrolling and occlusion checks are then skipped automatically (`hasLayout: false`) and the DOM is driven
// directly, so the agent still runs, with weaker guards.
// Jev calls go through `bin/jev raw --log browse`, so `jev tune browse` retrains the thresholds.
// Exit: 0 all pass, 1 any fail/uncertain, 3 Jev or browser unavailable.
import { spawn } from 'node:child_process';
import { existsSync, mkdirSync, readFileSync, realpathSync, writeFileSync } from 'node:fs';
import { homedir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';
import {
  compactSnapshot, buildStepQuestions, buildStepState, buildJudgeState, decideStep, stuckFromHistory,
  judgeFlow, personaData, recordStep, matchRecorded, recordingMatches, CHECKPOINT, HEALTH, PERSONAS,
} from './browse-core.mjs';
import { fieldContext, fieldText } from './text-helper.mjs';

const HERE = dirname(realpathSync(fileURLToPath(import.meta.url)));
const JEV = process.env.JEV_BIN || join(HERE, '..', '..', '..', 'bin', 'jev');
const require = createRequire(join(HERE, 'package.json'));
const SNAPSHOT_CHARS = 12000;
const STALE_RETRIES = 3;

const SNAPSHOT = readFileSync(join(HERE, 'snapshot.js'), 'utf8');
const EXECUTE = readFileSync(join(HERE, 'execute.js'), 'utf8');
const SETTLE = readFileSync(join(HERE, 'settle.js'), 'utf8');
const callWith = (src, arg) => `(${src})(${JSON.stringify(arg)})`;

function args(argv) {
  // Real Chrome by default: every geometric guard in this agent (visibility, viewport, occlusion, scroll)
  // needs a browser that lays the page out. --cdp opts into an external one (e.g. Lightpanda), which the
  // snapshot detects and degrades to DOM-only checks for.
  const o = { maxSteps: 15, json: false, chrome: true };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--json') o.json = true;
    else if (a === '--allow-submit') o.allowSubmit = true;
    else if (a === '--autofill') o.autofill = true;
    else if (a === '--observe') o.observe = true;
    else if (a === '--strict-freshness') o.strictFreshness = true;
    else if (a === '--login') o.login = true;
    else if (a === '--cache') o.cache = true;
    else if (a === '--re-record') { o.cache = true; o.reRecord = true; }
    else if (a === '--dom-input') o.domInput = true;
    else if (a === '--headful') o.headful = true;
    else if (a === '--chrome') o.chrome = true;
    else if (a.startsWith('--')) o[a.slice(2).replace(/-(\w)/g, (_, c) => c.toUpperCase())] = argv[++i];
  }
  o.maxSteps = Number(o.maxSteps);
  // --screenshots and --headful need a browser that paints, but an explicit --cdp already names one;
  // silently launching a second Chrome there would screenshot the wrong browser.
  if ((o.screenshots || o.headful) && !o.cdp) o.chrome = true;
  if (o.cdp) o.chrome = false;
  if (o.login) { o.profile = o.profile || 'default'; o.headful = true; }
  if (o.profile) o.chrome = true;
  return o;
}

// A persistent profile of its own, never the everyday one: Chrome 136+ refuses remote debugging on the
// default user-data-dir, and a test run has no business acting inside a live browsing session. Log in once
// per app with --login and every later run has those cookies.
const profileDir = (name) => join(homedir(), '.cache', 'jev-browse', 'profiles', name);

function findChrome() {
  if (process.env.JEV_BROWSER && existsSync(process.env.JEV_BROWSER)) return process.env.JEV_BROWSER;
  const candidates = process.platform === 'darwin'
    ? ['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', '/Applications/Chromium.app/Contents/MacOS/Chromium',
      '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge', '/Applications/Brave Browser.app/Contents/MacOS/Brave Browser']
    : ['/usr/bin/google-chrome', '/usr/bin/google-chrome-stable', '/usr/bin/chromium', '/usr/bin/chromium-browser', '/snap/bin/chromium'];
  return candidates.find((p) => existsSync(p));
}

const slug = (s) => String(s).toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 60) || 'flow';

const cachePath = (opt, flow, persona) => (opt.cache
  ? join(opt.cacheDir || '.jev-browse', `${slug(`${flow.name || flow.goal}-${persona}`)}.json`) : null);

function loadRecording(path) {
  if (!path || !existsSync(path)) return null;
  try { return JSON.parse(readFileSync(path, 'utf8')); } catch { return null; }
}

function saveRecording(path, recording) {
  try {
    mkdirSync(dirname(path), { recursive: true });
    writeFileSync(path, `${JSON.stringify(recording, null, 1)}\n`);
  } catch { /* a suite that cannot cache still runs */ }
}

let cost = 0;
function askJev(state, questions) {
  return new Promise((resolve) => {
    const p = spawn('python3', [JEV, 'raw', '--log', 'browse'], { stdio: ['pipe', 'pipe', 'pipe'] });
    let out = '';
    p.stdout.on('data', (d) => { out += d; });
    p.on('close', (code) => {
      if (code !== 0) return resolve(null);
      try {
        const r = JSON.parse(out);
        cost += r.usage?.cost || 0;
        resolve(r.answers || null);
      } catch { resolve(null); }
    });
    p.stdin.end(JSON.stringify({ state, questions }));
  });
}

// One atomic read of the page. Returns null while the document is navigating, so retry briefly.
//
// `settle` additionally waits for the page to have something to act on. `load` fires long before a React
// or Vue app has painted anything, so the first observation of an SPA saw an empty action table and the
// flow had nothing to choose from — EDUNEX's dashboard reported zero elements and simply could not start.
// An empty table means "not ready yet", which is a wait, not a decision, so it costs no Jev call.
async function observe(page, { settle = false } = {}) {
  let last = null;
  const tries = settle ? 20 : 10;
  for (let i = 0; i < tries; i++) {
    try {
      const o = await page.evaluate(SNAPSHOT);
      if (o) {
        last = o;
        if (!settle || o.actions.length) return o;
      }
    } catch { /* navigating mid-evaluate */ }
    await page.waitForTimeout(settle ? 400 : 40);
  }
  return last;
}

// Wait for the page to stop changing before judging it. `settle` only waits for SOMETHING actionable, which
// a login form already has, so the verdict was being taken mid-transition: EDUNEX swaps the login screen for
// its dashboard 4–10s after submit, and the judge saw the login form and called it `auth` on a login that
// had in fact succeeded. A page with a live region never fully stabilises, so this is best-effort and
// bounded — it buys a settled view where one exists and costs a few hundred ms where it does not.
async function quiesce(page, budgetMs = 10000) {
  const deadline = Date.now() + budgetMs;
  let previous = null;
  let last = null;
  while (Date.now() < deadline) {
    last = await observe(page, { settle: true });
    if (!last) return null;
    if (previous === last.marker) return last;
    previous = last.marker;
    await page.waitForTimeout(500);
  }
  return last;
}

// Resolves the operation + target Jev chose back onto an observed action. Model output is only ever an
// index into a table this process built; it never becomes a selector, a coordinate or a snippet.
function resolveAction(observation, operation, target) {
  if (operation === 'WAIT') return { kind: 'wait', label: 'wait' };
  if (operation.startsWith('SCROLL')) return observation.actions.find((a) => a.id === operation) || null;
  if (operation === 'SELECT') {
    const [index, option] = String(target).split(':');
    const a = observation.actions.find((x) => x.index === index && x.kind === 'select');
    const o = a && a.options[Number(option) - 1];
    // baseLabel keeps the element's own name; `label` is only for humans reading the run. The recording
    // must store the name the page will still have next run, not "Country → Morocco".
    return o ? { ...a, value: o.value, baseLabel: a.label, label: `${a.label} → ${o.label}` } : null;
  }
  const kind = operation === 'TYPE_TEXT' ? 'fill' : 'click';
  return observation.actions.find((a) => a.index === target && a.kind === kind) || null;
}

async function act(page, observation, action, text, opt) {
  const req = {
    node: action.node, kind: action.kind, value: action.value, text, delta: action.delta,
    guard: action.node != null ? observation.guards[action.node] : undefined,
    // Whole-page freshness is opt-in. A React app that re-renders its inputs mints new node ids, so the
    // page key differs on every poll and no decision survives to execute. The per-element guard below is
    // the property that keeps a click honest; --strict-freshness adds the page-wide check back for a
    // static page where any change at all should invalidate a decision.
    pageKey: opt.strictFreshness ? observation.pageKey : undefined,
    realInput: observation.hasLayout && !opt.domInput,
  };
  const r = await page.evaluate(callWith(EXECUTE, req)).catch(() => null);
  if (!r) return false;
  if (r.point) {
    await page.mouse.click(r.point.x, r.point.y);
    if (action.kind === 'fill') {
      await page.keyboard.press(process.platform === 'darwin' ? 'Meta+A' : 'Control+A');
      await page.keyboard.insertText(text);
    }
  }
  if (action.kind !== 'wait') {
    await page.evaluate(callWith(SETTLE, { node: action.node, kind: action.kind })).catch(() => {});
  } else {
    await page.waitForTimeout(150);
  }
  return true;
}

// Three ways to get a page, all behind one interface:
//  --profile NAME  a persistent Chrome profile of its own — ONE context holding the logins, a tab per flow,
//                  so every flow is signed in to whatever you signed into with --login.
//  default         the bundled Chrome — one browser, an isolated context per flow (no shared cookies).
//  --cdp URL       an already-running browser; Lightpanda allows one context per connection, so each flow
//                  opens its own connection.
async function openSession(chromium, opt) {
  const viewport = { width: 1366, height: 900 };
  if (opt.profile) {
    const dir = profileDir(opt.profile);
    mkdirSync(dir, { recursive: true });
    const exe = findChrome();
    if (!exe) { console.error('jev-browse: no Chrome/Chromium found; set JEV_BROWSER=/path/to/chrome'); process.exit(3); }
    const ctx = await chromium.launchPersistentContext(dir, {
      headless: !opt.headful, slowMo: opt.headful ? 250 : 0, executablePath: exe, viewport,
      args: ['--no-first-run', '--no-default-browser-check'],
    }).catch((e) => {
      console.error(`jev-browse: cannot open profile ${dir}: ${e.message}\n`
        + '  Another Chrome is probably already using it — close that window, or use a different --profile.');
      process.exit(3);
    });
    return { dir, newPage: async () => { const p = await ctx.newPage(); return { page: p, dispose: () => p.close().catch(() => {}) }; },
      close: () => ctx.close().catch(() => {}) };
  }
  if (opt.chrome) {
    const exe = findChrome();
    if (!exe) { console.error('jev-browse: no Chrome/Chromium found; set JEV_BROWSER=/path/to/chrome'); process.exit(3); }
    const browser = await chromium.launch({ headless: !opt.headful, slowMo: opt.headful ? 250 : 0, executablePath: exe,
      args: ['--no-sandbox', '--disable-dev-shm-usage'] });
    return { newPage: async () => { const c = await browser.newContext({ viewport }); return { page: await c.newPage(), dispose: () => c.close().catch(() => {}) }; },
      close: () => browser.close().catch(() => {}) };
  }
  try { await (await chromium.connectOverCDP(opt.cdp)).close(); } catch (e) {
    console.error(`jev-browse: no browser at ${opt.cdp}: ${e.message}`); process.exit(3);
  }
  return { newPage: async () => {
    const b = await chromium.connectOverCDP(opt.cdp);
    // A real Chrome reached over CDP already has a context holding the profile's cookies — open a TAB in it.
    // Calling newContext() there would hand back an empty, logged-out one, which is how a shared browser
    // silently stops being the signed-in browser you pointed at. Lightpanda exposes no context, so it falls
    // through to newContext(); closing the connection never kills a browser we did not start.
    const existing = b.contexts()[0];
    if (existing) {
      const page = await existing.newPage();
      return { page, dispose: async () => { await page.close().catch(() => {}); await b.close().catch(() => {}); } };
    }
    const c = await b.newContext();
    return { page: await c.newPage(), dispose: async () => { await c.close().catch(() => {}); await b.close().catch(() => {}); } };
  }, close: () => {} };
}

async function runFlow(session, flow, opt, persona = 'normal') {
  let page, dispose;
  try { ({ page, dispose } = await session.newPage()); } catch (e) {
    return { name: flow.name || flow.goal, persona, status: 'uncertain', cause: 'no_browser', detail: String(e.message).slice(0, 200), stop: 'no_browser', steps: [] };
  }
  const shots = [];
  const shotDir = opt.screenshots ? join(opt.screenshots, slug(`${flow.name || flow.goal}-${persona}`)) : null;
  if (shotDir) mkdirSync(shotDir, { recursive: true });
  const shot = async (name, fullPage = false) => {
    if (!shotDir) return;
    const p = join(shotDir, `${name}.png`);
    try { await page.screenshot({ path: p, fullPage }); shots.push(p); } catch { /* keep going without it */ }
  };
  const errors = [];
  page.on('pageerror', (e) => errors.push(e.message));
  const data = personaData(persona, flow.data || {});
  const history = [];
  let stop = 'max_steps';
  let stale = 0;
  // A recording replays at L0 with no model call. It is abandoned the moment a recorded step no longer
  // matches the page — that mismatch IS the "the UI changed" signal — and the rest of the flow falls back
  // to Jev, which re-records on the way out.
  const cache = cachePath(opt, flow, persona);
  const saved = loadRecording(cache);
  let replaying = !!(saved && recordingMatches(saved, flow, persona) && !opt.reRecord);
  let jevCalls = 0;
  const fresh = [];
  try {
    await page.goto(flow.url, { waitUntil: 'load' });
    for (let step = 0; step < opt.maxSteps; step++) {
      const obs = await observe(page, { settle: true });
      if (!obs) { stop = 'no_document'; break; }

      let operation = null, action = null, fillKey = null;
      if (replaying) {
        const rec = saved.steps[fresh.length];
        if (!rec) { stop = 'replayed'; break; }           // the recording ran to its end
        action = matchRecorded(rec, obs.actions);
        if (action) { operation = rec.operation; fillKey = rec.fillKey ?? null; }
        else { replaying = false; }                        // the page moved on; Jev takes over from here
      }
      if (!action) {
        const questions = buildStepQuestions(obs, data, opt);
        const state = buildStepState(flow.goal, obs, history, data);
        jevCalls++;
        const d = decideStep(await askJev(state, questions), questions, data);
        if (d.stop) { stop = d.stop; break; }
        action = resolveAction(obs, d.operation, d.target);
        if (!action) { stop = 'stuck'; break; }
        operation = d.operation;
        fillKey = d.fills.length ? d.fills[0].key : null;
      }

      let text = null;
      if (operation === 'TYPE_TEXT') {
        if (fillKey != null && fillKey in data) text = data[fillKey] ?? '';
        else if (opt.autofill) text = await fieldText(fieldContext(flow.goal, action, obs, history), { secret: action.secret });
        // No value for this field is a skipped step, not the end of the flow; three of them in a row is
        // what the stuck detector is for.
        if (text == null) {
          history.push({ operation, action: `TYPE_TEXT "${action.label}" — no value available`, changed: false });
          if (stuckFromHistory(history)) { stop = 'no_value'; break; }
          continue;
        }
      }

      if (opt.headful && action.node != null) {
        await page.evaluate(callWith(`((n) => {
          const t = window.__jevBrowse?.nodes.get(n);
          if (t) { t.scrollIntoView({ block: 'center' }); t.style.outline = '3px solid #e11d48'; t.style.outlineOffset = '2px'; }
        })`, action.node)).catch(() => {});
        await page.waitForTimeout(700);
      }
      await shot(String(step + 1).padStart(2, '0'));

      const before = obs.marker;
      if (!await act(page, obs, action, text, opt)) {
        // The page changed between the decision and the input: re-observe rather than click the wrong thing.
        if (++stale > STALE_RETRIES) { stop = 'stale'; break; }
        step--;   // a rejected decision is not one of the flow's steps
        continue;
      }
      stale = 0;
      fresh.push(recordStep(operation, action, fillKey));
      if (persona === 'double_submit' && action.kind === 'click') await act(page, obs, action, null, opt);
      if (persona === 'back_button' && step === 0) { await page.goBack().catch(() => {}); await page.waitForTimeout(300); }

      const after = await observe(page);
      history.push({
        operation,
        action: ['wait', 'scroll'].includes(action.kind) ? operation
          : `${operation} "${action.label}"${text ? ` = ${action.secret ? '•••' : text}` : ''}`,
        changed: after ? after.marker !== before : true,
      });
      if (stuckFromHistory(history)) { stop = 'loop'; break; }
    }

    const judge = persona === 'normal' && flow.expect ? CHECKPOINT : HEALTH;
    const final = await quiesce(page);
    const state = buildJudgeState(
      flow.expect || 'the app handles the session gracefully',
      new URL(page.url()).pathname,
      await fullPageText(page),
      { nativeValidation: final?.nativeValidation || [], persona },
    );
    // The judge is NEVER replayed from cache. It is the assertion — caching it would make a green run mean
    // "it was green once", which is how a suite quietly stops testing anything.
    jevCalls++;
    const verdict = judgeFlow(await askJev(state, judge), errors);
    await shot('final');
    await shot('final-full', true);
    if (cache && verdict.status === 'pass' && fresh.length) {
      saveRecording(cache, { version: 1, persona, url: flow.url, goal: flow.goal, expect: flow.expect ?? null,
        recorded_at: new Date().toISOString(), steps: fresh });
    }
    return { name: flow.name || flow.goal, persona, ...verdict, stop, steps: history.map((h) => h.action),
      url: page.url(), screenshots: shots, jev_calls: jevCalls, replayed: replaying };
  } catch (e) {
    await shot('error');
    return { name: flow.name || flow.goal, persona, status: 'uncertain', cause: 'driver_error', detail: String(e.message || e).slice(0, 200), stop, steps: history.map((h) => h.action), screenshots: shots };
  } finally {
    await dispose();
  }
}

// The step loop reads viewport-only text; the final judge needs the whole page, footer included.
async function fullPageText(page) {
  try {
    return compactSnapshot(await page.locator('body').ariaSnapshot(), SNAPSHOT_CHARS);
  } catch {
    return compactSnapshot(await page.evaluate(() => document.body?.innerText || '').catch(() => ''), SNAPSHOT_CHARS);
  }
}

async function main() {
  const opt = args(process.argv.slice(2));
  let flows;
  if (opt.flows) flows = JSON.parse(readFileSync(opt.flows, 'utf8'));
  else if (opt.url && (opt.goal || opt.login)) flows = [{ url: opt.url, goal: opt.goal, expect: opt.expect, data: opt.data ? JSON.parse(opt.data) : {} }];
  else if (opt.login) flows = [{ url: 'about:blank' }];
  else { console.error('usage: jev-browse --url URL --goal "…" [--expect "…"] [--data JSON] [--adversarial N] | --flows flows.json\n       jev-browse --login --profile NAME --url URL   sign in once; later runs reuse the session'); process.exit(64); }

  const { chromium } = require('playwright-core');
  const session = await openSession(chromium, opt);

  // --login: open the persistent profile and hand the keyboard to the user. Nothing is automated and no
  // credential passes through this process — you sign in yourself, close the window, and the cookies stay
  // in the profile for every later run.
  if (opt.login) {
    const { page } = await session.newPage();
    await page.goto(flows[0].url, { waitUntil: 'load' }).catch(() => {});
    console.error(`jev-browse: signed-in profile at ${session.dir}\n`
      + '  Log in in the window that just opened, then CLOSE IT to save the session.');
    await page.waitForEvent('close', { timeout: 0 }).catch(() => {});
    await session.close();
    process.exit(0);
  }

  // --observe: print the page exactly as Jev is offered it, and make no decision. The fastest way to find
  // out why a flow never sees the button you expected.
  if (opt.observe) {
    const { page } = await session.newPage();
    await page.goto(flows[0].url, { waitUntil: 'load' });
    const obs = await observe(page, { settle: true });
    const data = flows[0].data || {};
    console.log(JSON.stringify({
      url: obs?.url, hasLayout: obs?.hasLayout, scroll: obs?.scroll, omitted: obs?.omitted,
      offered: buildStepQuestions(obs, data, opt),
      state: buildStepState(flows[0].goal || '', obs, [], data),
    }, null, 1));
    await session.close();
    process.exit(0);
  }

  const tasks = [];
  for (const f of flows) {
    if (opt.adversarial) {
      const n = Number(opt.adversarial);
      for (let i = 0; i < n; i++) tasks.push(() => runFlow(session, f, opt, PERSONAS[i % PERSONAS.length]));
    } else tasks.push(() => runFlow(session, f, opt, 'normal'));
  }
  const t = Date.now();
  // Headful runs one flow at a time so there is one window to watch; everything else runs in parallel.
  const results = [];
  if (opt.headful) for (const task of tasks) results.push(await task());
  else results.push(...await Promise.all(tasks.map((task) => task())));
  await session.close();
  const bad = results.filter((r) => r.status !== 'pass');
  const summary = { runs: results.length, pass: results.length - bad.length, fail: bad.filter((r) => r.status === 'fail').length, uncertain: bad.filter((r) => r.status === 'uncertain').length, seconds: (Date.now() - t) / 1000, cost_usd: Number(cost.toFixed(6)) };
  if (opt.json) console.log(JSON.stringify({ ...summary, results }, null, 1));
  else {
    for (const r of results) console.log(`${r.status.toUpperCase().padEnd(9)} ${r.persona.padEnd(13)} ${r.name}  cause=${r.cause} stop=${r.stop} steps=${r.steps.length}${r.jev_calls != null ? ` jev=${r.jev_calls}${r.replayed ? ' (replayed)' : ''}` : ''}${r.detail ? `  ${JSON.stringify(r.detail)}` : ''}`);
    console.log(`runs ${summary.runs}  pass ${summary.pass}  fail ${summary.fail}  uncertain ${summary.uncertain}  jev calls ${results.reduce((n, r) => n + (r.jev_calls || 0), 0)}  ${summary.seconds}s  $${summary.cost_usd}`);
  }
  if (results.every((r) => r.cause === 'jev_unavailable')) process.exit(3);
  process.exit(bad.length ? 1 : 0);
}

main();
