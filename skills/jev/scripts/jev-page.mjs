#!/usr/bin/env node
// jev-page — the jev-browse policy, for a page someone ELSE is driving.
//
// jev-browse owns its browser. This does not: it takes one page state on stdin and prints what Jev decides,
// so Claude driving the real Chrome through claude-in-chrome (or any other driver) gets the same operation
// table, the same rules, the same answer validation — instead of eyeballing a screenshot and guessing.
//
//   1. inject skills/jev/scripts/snapshot.js into the tab   -> page state JSON
//   2. echo "$state" | jev-page --goal "…"                  -> {"operation":"CLICK","target":"3", …}
//   3. execute element [3] in the tab, repeat
//
//   echo "$state" | jev-page --goal "find the pricing page"
//   echo "$state" | jev-page --goal "log in" --data '{"email":"qa@x.co"}'
//   echo "$state" | jev-page --expect "the cart shows 2 items"        # judge instead of decide
//   echo "$state" | jev-page --goal "…" --questions                   # print the questions, ask nothing
//
// Stdin accepts the snapshot.js object verbatim; only url/title/text/actions are read. Exit 0 with a
// decision, 2 when Jev declines to act (stop), 3 when Jev is unreachable — never a guess.
import { spawn } from 'node:child_process';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { readFileSync, realpathSync } from 'node:fs';
import {
  buildStepQuestions, buildStepState, buildJudgeState, decideStep, judgeFlow, CHECKPOINT,
} from './browse-core.mjs';

const HERE = dirname(realpathSync(fileURLToPath(import.meta.url)));
const JEV = process.env.JEV_BIN || join(HERE, '..', '..', '..', 'bin', 'jev');

function args(argv) {
  const o = {};
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--questions') o.questionsOnly = true;
    else if (a === '--snapshot-js') o.snapshotJs = true;
    else if (a === '--allow-submit') o.allowSubmit = true;
    else if (a === '--autofill') o.autofill = true;
    else if (a.startsWith('--')) o[a.slice(2).replace(/-(\w)/g, (_, c) => c.toUpperCase())] = argv[++i];
  }
  return o;
}

const readStdin = () => new Promise((resolve, reject) => {
  let s = '';
  process.stdin.setEncoding('utf8');
  process.stdin.on('data', (d) => { s += d; });
  process.stdin.on('end', () => { try { resolve(JSON.parse(s)); } catch (e) { reject(e); } });
});

function askJev(state, questions) {
  return new Promise((resolve) => {
    const p = spawn('python3', [JEV, 'raw', '--log', 'browse'], { stdio: ['pipe', 'pipe', 'inherit'] });
    let out = '';
    p.stdout.on('data', (d) => { out += d; });
    p.on('error', () => resolve(null));
    p.on('close', (code) => {
      if (code !== 0) return resolve(null);
      try { resolve(JSON.parse(out)); } catch { resolve(null); }
    });
    p.stdin.end(JSON.stringify({ state, questions }));
  });
}

async function main() {
  const opt = args(process.argv.slice(2));
  // The exact observer to paste into the driver's evaluate/javascript_tool. Printing it beats retyping it:
  // the page state this tool parses is whatever THIS file's snapshot.js produces.
  if (opt.snapshotJs) { process.stdout.write(readFileSync(join(HERE, 'snapshot.js'), 'utf8')); process.exit(0); }
  if (!opt.goal && !opt.expect) {
    console.error('usage: <page state json> | jev-page --goal "…" [--data JSON] [--allow-submit] [--autofill]\n'
      + '       <page state json> | jev-page --expect "…"    judge the page instead of choosing an action');
    process.exit(64);
  }
  let obs;
  try { obs = await readStdin(); } catch (e) { console.error(`jev-page: stdin is not JSON: ${e.message}`); process.exit(64); }
  if (!obs || !Array.isArray(obs.actions)) { console.error('jev-page: expected the snapshot.js object (needs .actions)'); process.exit(64); }
  const data = opt.data ? JSON.parse(opt.data) : {};

  // Judge mode: the same verdict + cause checkpoint jev-browse ends a flow with.
  if (!opt.goal) {
    const state = buildJudgeState(opt.expect, obs.url, String(obs.text || '').slice(0, 12000));
    const res = await askJev(state, CHECKPOINT);
    if (!res) { console.error('jev-page: Jev unavailable'); process.exit(3); }
    console.log(JSON.stringify({ ...judgeFlow(res.answers, []), usage: res.usage }, null, 1));
    process.exit(0);
  }

  const questions = buildStepQuestions(obs, data, opt);
  if (opt.questionsOnly) { console.log(JSON.stringify(questions, null, 1)); process.exit(0); }
  const state = buildStepState(opt.goal, obs, opt.history ? JSON.parse(opt.history) : [], data);
  const res = await askJev(state, questions);
  if (!res) { console.error('jev-page: Jev unavailable'); process.exit(3); }

  const d = decideStep(res.answers, questions, data);
  const chosen = d.target != null
    ? obs.actions.find((a) => a.index === String(d.target).split(':')[0])
    : null;
  const out = {
    operation: d.operation, target: d.target ?? null, stop: d.stop ?? null,
    element: chosen ? `[${chosen.index}] ${chosen.role} "${chosen.label}"` : null,
    node: chosen ? chosen.node : null,
    text: d.fills.length ? d.fills[0].text : null,
    confidence: res.answers?.operation?.confidence ?? null,
    usage: res.usage,
  };
  console.log(JSON.stringify(out, null, 1));
  process.exit(d.stop ? 2 : 0);
}

main();
