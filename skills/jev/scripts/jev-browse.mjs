#!/usr/bin/env node
// jev-browse — System 1 browser agent: Jev picks every fill and click, an LLM only sees the failures.
//
//   jev-browse --url URL --goal "log in" --expect "dashboard shows today sales" [--data '{"email":"a@b.co"}']
//   jev-browse --flows flows.json        [{name, url, goal, expect, data}], run in parallel
//   jev-browse --url URL --goal … --adversarial N   N parallel sessions over the personas
//              (normal, invalid_input, hostile_input, double_submit, back_button); reports only broken ones
//   options: --cdp URL (default $JEV_BROWSE_CDP or http://127.0.0.1:9222, Lightpanda) --max-steps 15 --json
//            --allow-submit   let a flow without --data press form buttons (off by default)
//            --headful        real, visible Chrome window: flows run one at a time, slowed down, and each element
//                             is outlined before Jev clicks it, so you can watch
//            --chrome         headless Chrome instead of Lightpanda (needed for screenshots)
//            --screenshots D  save D/<flow>/NN.png per step plus final.png and final-full.png (implies --chrome);
//                             Jev is text-only, so layout/visual checks are a vision model reading these (L3)
//
// Read-only by default: without --data or --allow-submit it never presses a button inside a form, and it
// never follows a link off the site under test (they are listed to Jev as external_links instead).
//
// Drives the DOM directly (native value setter + input/change events, element.click()) because Lightpanda
// has no layout, so Playwright's visibility checks never pass there; the same code works on Chromium.
// Jev calls go through `bin/jev raw --log browse`, so `jev tune browse` retrains the thresholds.
// Exit: 0 all pass, 1 any fail/uncertain, 3 Jev or browser unavailable.
import { spawn } from 'node:child_process';
import { existsSync, mkdirSync, readFileSync, realpathSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';
import { compactSnapshot, buildStepQuestions, buildStepState, buildJudgeState, decideStep, judgeFlow, personaData, CHECKPOINT, HEALTH, PERSONAS } from './browse-core.mjs';

const HERE = dirname(realpathSync(fileURLToPath(import.meta.url)));
const JEV = process.env.JEV_BIN || join(HERE, '..', '..', '..', 'bin', 'jev');
const require = createRequire(join(HERE, 'package.json'));
const SNAPSHOT_CHARS = 12000;

function args(argv) {
  const o = { cdp: process.env.JEV_BROWSE_CDP || 'http://127.0.0.1:9222', maxSteps: 15, json: false };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--json') o.json = true;
    else if (a === '--allow-submit') o.allowSubmit = true;
    else if (a === '--headful') o.headful = true;
    else if (a === '--chrome') o.chrome = true;
    else if (a.startsWith('--')) o[a.slice(2).replace(/-(\w)/g, (_, c) => c.toUpperCase())] = argv[++i];
  }
  o.maxSteps = Number(o.maxSteps);
  if (o.screenshots || o.headful) o.chrome = true;
  return o;
}

function findChrome() {
  if (process.env.JEV_BROWSER && existsSync(process.env.JEV_BROWSER)) return process.env.JEV_BROWSER;
  const candidates = process.platform === 'darwin'
    ? ['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', '/Applications/Chromium.app/Contents/MacOS/Chromium',
      '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge', '/Applications/Brave Browser.app/Contents/MacOS/Brave Browser']
    : ['/usr/bin/google-chrome', '/usr/bin/google-chrome-stable', '/usr/bin/chromium', '/usr/bin/chromium-browser', '/snap/bin/chromium'];
  return candidates.find((p) => existsSync(p));
}

const slug = (s) => String(s).toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 60) || 'flow';

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

async function elements(page) {
  return page.evaluate(() => {
    const label = (e) => {
      const byFor = e.id && document.querySelector(`label[for="${e.id}"]`);
      const wrap = e.closest('label');
      return (e.getAttribute('aria-label') || byFor?.textContent || wrap?.textContent || e.placeholder
        || e.innerText || e.value || e.name || e.getAttribute('href') || '').trim().replace(/\s+/g, ' ').slice(0, 60);
    };
    const out = [];
    [...document.querySelectorAll('a[href],button,input,select,textarea,[role=button]')].forEach((e, i) => {
      if (e.type === 'hidden' || e.disabled) return;
      e.setAttribute('data-jev', String(i));
      const tag = e.tagName.toLowerCase();
      const isButton = tag === 'button' || e.getAttribute('role') === 'button' || ['submit', 'button'].includes(e.type);
      const kind = tag === 'a' ? 'link' : isButton ? 'button' : 'input';
      let external = false;
      if (tag === 'a') {
        try {
          const u = new URL(e.getAttribute('href'), location.href);
          external = !['http:', 'https:'].includes(u.protocol) || u.hostname.replace(/^www\./, '') !== location.hostname.replace(/^www\./, '');
        } catch { external = true; }
      }
      out.push({ id: i, kind, label: label(e), type: e.type || tag, href: tag === 'a' ? e.getAttribute('href') : undefined,
        external, inForm: isButton && !!e.closest('form'), empty: kind === 'input' ? !e.value : undefined });
    });
    return out;
  });
}

async function snapshot(page) {
  try {
    return compactSnapshot(await page.locator('body').ariaSnapshot(), SNAPSHOT_CHARS);
  } catch {
    return compactSnapshot(await page.evaluate(() => document.body?.innerText || ''), SNAPSHOT_CHARS);
  }
}

const fill = (page, id, value) => page.evaluate(({ id, value }) => {
  const el = document.querySelector(`[data-jev="${id}"]`);
  if (!el) return;
  const setter = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(el), 'value')?.set;
  setter ? setter.call(el, value) : (el.value = value);
  el.dispatchEvent(new Event('input', { bubbles: true }));
  el.dispatchEvent(new Event('change', { bubbles: true }));
}, { id, value });

async function click(page, el) {
  if (el.kind === 'link' && el.href && !el.href.startsWith('#') && !el.href.startsWith('javascript:')) {
    await page.goto(new URL(el.href, page.url()).href, { waitUntil: 'load' });
  } else {
    await page.evaluate((id) => document.querySelector(`[data-jev="${id}"]`)?.click(), el.id);
  }
  await page.waitForTimeout(400);
}

async function runFlow(chromium, flow, opt, persona = 'normal', shared = null) {
  // Chrome (--chrome/--headful): one shared browser, a context per flow. Lightpanda: one CDP connection per
  // session, because it allows a single browser context per connection.
  let browser = shared;
  if (!browser) {
    try { browser = await chromium.connectOverCDP(opt.cdp); } catch (e) {
      return { name: flow.name || flow.goal, persona, status: 'uncertain', cause: 'no_browser', detail: String(e.message).slice(0, 200), stop: 'no_browser', steps: [] };
    }
  }
  let ctx = null;
  let page = null;
  const shots = [];
  const shotDir = opt.screenshots ? join(opt.screenshots, slug(`${flow.name || flow.goal}-${persona}`)) : null;
  if (shotDir) mkdirSync(shotDir, { recursive: true });
  const shot = async (name, fullPage = false) => {
    if (!shotDir) return;
    const p = join(shotDir, `${name}.png`);
    try { await page.screenshot({ path: p, fullPage }); shots.push(p); } catch { /* keep going without it */ }
  };
  const errors = [];
  const data = personaData(persona, flow.data || {});
  const history = [];
  let stop = 'max_steps';
  let lastClick = null;
  let repeats = 0;
  try {
    ctx = await browser.newContext(shared ? { viewport: { width: 1366, height: 900 } } : {});
    page = await ctx.newPage();
    page.on('pageerror', (e) => errors.push(e.message));
    await page.goto(flow.url, { waitUntil: 'load' });
    for (let step = 0; step < opt.maxSteps; step++) {
      const els = await elements(page);
      const state = buildStepState(flow.goal, new URL(page.url()).pathname, await snapshot(page), history, els, data);
      const d = decideStep(await askJev(state, buildStepQuestions(els, data, { allowSubmit: opt.allowSubmit })));
      for (const f of d.fills) await fill(page, f.id, data[f.key]);
      if (d.stop) { stop = d.stop; break; }
      const el = els.find((e) => e.id === d.click);
      if (!el) { stop = 'stuck'; break; }
      repeats = d.click === lastClick ? repeats + 1 : 0;
      if (repeats >= 2) { stop = 'loop'; break; }
      lastClick = d.click;
      history.push(`${d.fills.length ? `filled ${d.fills.map((f) => f.key).join(', ')}; ` : ''}clicked ${el.kind} "${el.label}"`);
      if (opt.headful) {
        await page.evaluate((id) => {
          const t = document.querySelector(`[data-jev="${id}"]`);
          if (t) { t.scrollIntoView({ block: 'center' }); t.style.outline = '3px solid #e11d48'; t.style.outlineOffset = '2px'; }
        }, el.id).catch(() => {});
        await page.waitForTimeout(700);
      }
      await shot(String(step + 1).padStart(2, '0'));
      await click(page, el);
      if (persona === 'double_submit' && el.kind === 'button') await click(page, el);
      if (persona === 'back_button' && step === 0) { await page.goBack().catch(() => {}); await page.waitForTimeout(300); }
    }
    const judge = persona === 'normal' && flow.expect ? CHECKPOINT : HEALTH;
    // Native constraint validation (type=email, required) blocks submit with a tooltip outside the DOM.
    const nativeValidation = await page.evaluate(() => [...document.querySelectorAll('input,select,textarea')]
      .filter((e) => e.validity && !e.validity.valid && e.validationMessage)
      .map((e) => `${e.name || e.id || e.type}: ${e.validationMessage}`)).catch(() => []);
    const state = buildJudgeState(flow.expect || 'the app handles the session gracefully', new URL(page.url()).pathname,
      await snapshot(page), { nativeValidation, persona });
    const verdict = judgeFlow(await askJev(state, judge), errors);
    await shot('final');
    await shot('final-full', true);
    return { name: flow.name || flow.goal, persona, ...verdict, stop, steps: history, url: page.url(), screenshots: shots };
  } catch (e) {
    await shot('error');
    return { name: flow.name || flow.goal, persona, status: 'uncertain', cause: 'driver_error', detail: String(e.message || e).slice(0, 200), stop, steps: history, screenshots: shots };
  } finally {
    if (ctx) await ctx.close().catch(() => {});
    if (!shared) await browser.close().catch(() => {});
  }
}

async function main() {
  const opt = args(process.argv.slice(2));
  let flows;
  if (opt.flows) flows = JSON.parse(readFileSync(opt.flows, 'utf8'));
  else if (opt.url && opt.goal) flows = [{ url: opt.url, goal: opt.goal, expect: opt.expect, data: opt.data ? JSON.parse(opt.data) : {} }];
  else { console.error('usage: jev-browse --url URL --goal "…" [--expect "…"] [--data JSON] [--adversarial N] | --flows flows.json'); process.exit(64); }

  const { chromium } = require('playwright-core');
  let shared = null;
  if (opt.chrome) {
    const exe = findChrome();
    if (!exe) { console.error('jev-browse: no Chrome/Chromium found; set JEV_BROWSER=/path/to/chrome'); process.exit(3); }
    shared = await chromium.launch({ headless: !opt.headful, slowMo: opt.headful ? 250 : 0, executablePath: exe,
      args: ['--no-sandbox', '--disable-dev-shm-usage'] });
  } else {
    try { await (await chromium.connectOverCDP(opt.cdp)).close(); } catch (e) { console.error(`jev-browse: no browser at ${opt.cdp}: ${e.message}`); process.exit(3); }
  }

  const tasks = [];
  for (const f of flows) {
    if (opt.adversarial) {
      const n = Number(opt.adversarial);
      for (let i = 0; i < n; i++) tasks.push(() => runFlow(chromium, f, opt, PERSONAS[i % PERSONAS.length], shared));
    } else tasks.push(() => runFlow(chromium, f, opt, 'normal', shared));
  }
  const t = Date.now();
  // Headful runs one flow at a time so there is one window to watch; everything else runs in parallel.
  const results = [];
  if (opt.headful) for (const task of tasks) results.push(await task());
  else results.push(...await Promise.all(tasks.map((task) => task())));
  if (shared) await shared.close().catch(() => {});
  const bad = results.filter((r) => r.status !== 'pass');
  const summary = { runs: results.length, pass: results.length - bad.length, fail: bad.filter((r) => r.status === 'fail').length, uncertain: bad.filter((r) => r.status === 'uncertain').length, seconds: (Date.now() - t) / 1000, cost_usd: Number(cost.toFixed(6)) };
  if (opt.json) console.log(JSON.stringify({ ...summary, results }, null, 1));
  else {
    for (const r of results) console.log(`${r.status.toUpperCase().padEnd(9)} ${r.persona.padEnd(13)} ${r.name}  cause=${r.cause} stop=${r.stop} steps=${r.steps.length}${r.detail ? `  ${JSON.stringify(r.detail)}` : ''}`);
    console.log(`runs ${summary.runs}  pass ${summary.pass}  fail ${summary.fail}  uncertain ${summary.uncertain}  ${summary.seconds}s  $${summary.cost_usd}`);
  }
  if (results.every((r) => r.cause === 'jev_unavailable')) process.exit(3);
  process.exit(bad.length ? 1 : 0);
}

main().catch((e) => { console.error(`jev-browse: ${e.message || e}`); process.exit(3); });
