#!/usr/bin/env node
// jev-browse — System 1 browser agent: Jev picks every fill and click, an LLM only sees the failures.
//
//   jev-browse --url URL --goal "log in" --expect "dashboard shows today sales" [--data '{"email":"a@b.co"}']
//   jev-browse --flows flows.json        [{name, url, goal, expect, data}], run in parallel
//   jev-browse --url URL --goal … --adversarial N   N parallel sessions over the personas
//              (normal, invalid_input, hostile_input, double_submit, back_button); reports only broken ones
//   options: --cdp URL (default $JEV_BROWSE_CDP or http://127.0.0.1:9222, Lightpanda) --max-steps 15 --json
//
// Drives the DOM directly (native value setter + input/change events, element.click()) because Lightpanda
// has no layout, so Playwright's visibility checks never pass there; the same code works on Chromium.
// Jev calls go through `bin/jev raw --log browse`, so `jev tune browse` retrains the thresholds.
// Exit: 0 all pass, 1 any fail/uncertain, 3 Jev or browser unavailable.
import { spawn } from 'node:child_process';
import { readFileSync, realpathSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';
import { buildStepQuestions, buildStepState, buildJudgeState, decideStep, judgeFlow, personaData, CHECKPOINT, HEALTH, PERSONAS } from './browse-core.mjs';

const HERE = dirname(realpathSync(fileURLToPath(import.meta.url)));
const JEV = process.env.JEV_BIN || join(HERE, '..', '..', '..', 'bin', 'jev');
const require = createRequire(join(HERE, 'package.json'));
const SNAPSHOT_CHARS = 6000;

function args(argv) {
  const o = { cdp: process.env.JEV_BROWSE_CDP || 'http://127.0.0.1:9222', maxSteps: 15, json: false };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--json') o.json = true;
    else if (a.startsWith('--')) o[a.slice(2).replace(/-(\w)/g, (_, c) => c.toUpperCase())] = argv[++i];
  }
  o.maxSteps = Number(o.maxSteps);
  return o;
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
      out.push({ id: i, kind, label: label(e), type: e.type || tag, href: tag === 'a' ? e.getAttribute('href') : undefined, empty: kind === 'input' ? !e.value : undefined });
    });
    return out;
  });
}

async function snapshot(page) {
  for (const sel of ['main', 'body']) {
    try {
      if (await page.locator(sel).count()) return (await page.locator(sel).first().ariaSnapshot()).slice(0, SNAPSHOT_CHARS);
    } catch { /* fall through */ }
  }
  return (await page.evaluate(() => document.body?.innerText || '')).slice(0, SNAPSHOT_CHARS);
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

async function runFlow(chromium, flow, opt, persona = 'normal') {
  // One CDP connection per session: Lightpanda allows a single browser context per connection.
  let browser;
  try { browser = await chromium.connectOverCDP(opt.cdp); } catch (e) {
    return { name: flow.name || flow.goal, persona, status: 'uncertain', cause: 'no_browser', detail: String(e.message).slice(0, 200), stop: 'no_browser', steps: [] };
  }
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', (e) => errors.push(e.message));
  const data = personaData(persona, flow.data || {});
  const history = [];
  let stop = 'max_steps';
  let lastClick = null;
  let repeats = 0;
  try {
    await page.goto(flow.url, { waitUntil: 'load' });
    for (let step = 0; step < opt.maxSteps; step++) {
      const els = await elements(page);
      const state = buildStepState(flow.goal, new URL(page.url()).pathname, await snapshot(page), history, els, data);
      const d = decideStep(await askJev(state, buildStepQuestions(els, data)));
      for (const f of d.fills) await fill(page, f.id, data[f.key]);
      if (d.stop) { stop = d.stop; break; }
      const el = els.find((e) => e.id === d.click);
      if (!el) { stop = 'stuck'; break; }
      repeats = d.click === lastClick ? repeats + 1 : 0;
      if (repeats >= 2) { stop = 'loop'; break; }
      lastClick = d.click;
      history.push(`${d.fills.length ? `filled ${d.fills.map((f) => f.key).join(', ')}; ` : ''}clicked ${el.kind} "${el.label}"`);
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
    return { name: flow.name || flow.goal, persona, ...verdict, stop, steps: history, url: page.url() };
  } catch (e) {
    return { name: flow.name || flow.goal, persona, status: 'uncertain', cause: 'driver_error', detail: String(e.message || e).slice(0, 200), stop, steps: history };
  } finally {
    await ctx.close().catch(() => {});
    await browser.close().catch(() => {});
  }
}

async function main() {
  const opt = args(process.argv.slice(2));
  let flows;
  if (opt.flows) flows = JSON.parse(readFileSync(opt.flows, 'utf8'));
  else if (opt.url && opt.goal) flows = [{ url: opt.url, goal: opt.goal, expect: opt.expect, data: opt.data ? JSON.parse(opt.data) : {} }];
  else { console.error('usage: jev-browse --url URL --goal "…" [--expect "…"] [--data JSON] [--adversarial N] | --flows flows.json'); process.exit(64); }

  const { chromium } = require('playwright-core');
  try { await (await chromium.connectOverCDP(opt.cdp)).close(); } catch (e) { console.error(`jev-browse: no browser at ${opt.cdp}: ${e.message}`); process.exit(3); }

  const jobs = [];
  for (const f of flows) {
    if (opt.adversarial) {
      const n = Number(opt.adversarial);
      for (let i = 0; i < n; i++) jobs.push(runFlow(chromium, f, opt, PERSONAS[i % PERSONAS.length]));
    } else jobs.push(runFlow(chromium, f, opt));
  }
  const t = Date.now();
  const results = await Promise.all(jobs);
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

main();
