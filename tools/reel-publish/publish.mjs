#!/usr/bin/env node
// reel-publish <post.json> [--only a,b] [--dry-run] [--yes]
//        reel-publish pair          (once: write the bridge secret, then reload File Drop Bridge)
//        reel-publish check-login   (open each site in a bridge tab, report signed in / SIGNED OUT)
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { loadPost, selectPlatforms, pendingPlatforms, scheduleParts } from './lib/post.mjs';
import { readResults, recordResult } from './lib/results.mjs';
import { Bridge, readSecret, pair } from './lib/bridge.mjs';

const HOME_DIR = path.join(os.homedir(), '.reel-publish');
const LOGIN_CHECKS = [
  ['tiktok', 'https://www.tiktok.com/tiktokstudio/upload', /\/login/],
  ['facebook_profile', 'https://www.facebook.com/reels/create/', /login/],
  ['facebook_page', 'https://business.facebook.com/latest/home?asset_id=1290399254155522', /loginpage|\/login/],
  ['linkedin', 'https://www.linkedin.com/feed/', /\/login|authwall|\/uas\//],
  ['drive', 'https://drive.google.com/drive/u/1/', /accounts\.google|workspace\.google/],
];

function parseArgs(argv) {
  const args = { file: null, only: null, dryRun: false, yes: false, command: null };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--only') args.only = (argv[++i] || '').split(',').filter(Boolean);
    else if (a === '--dry-run') args.dryRun = true;
    else if (a === '--yes') args.yes = true;
    else if (a === 'pair' || a === 'check-login') args.command = a;
    else if (!args.file) args.file = a;
    else throw new Error(`unexpected argument ${a}`);
  }
  return args;
}

function printPlan(post, names) {
  const lines = [`PLAN for ${post.slug} (${post.video})`,
    post.schedule ? `schedule: ${scheduleParts(post.schedule).iso}` : 'schedule: now'];
  for (const n of names) {
    const p = post.platforms[n];
    const text = p.title || p.caption || p.text || p.description || '';
    lines.push(`  - ${n}: ${text ? JSON.stringify(text.slice(0, 120)) : '(no text)'}`);
  }
  lines.push(post.yes ? '' : 'nothing posted: re-run with --yes to publish, or --dry-run to rehearse');
  return lines.join('\n');
}

// One Bridge per run, started on first use. A failed start is remembered so later platforms fail at once.
function makeShared() {
  let bridge = null;
  let ready = null;
  return {
    newPage() {
      ready ||= (async () => {
        bridge = new Bridge({ secret: readSecret() });
        await bridge.connect({ timeout: 90_000 });
      })();
      return ready.then(() => bridge.newPage());
    },
    close: async () => { if (bridge) await bridge.close().catch(() => {}); },
  };
}

function doPair() {
  const { secretFile, jsFile } = pair();
  console.log(`wrote ${secretFile} and ${jsFile}`);
  console.log('Reload File Drop Bridge at chrome://extensions (one time)');
  return 0;
}

async function checkLogin() {
  const shared = makeShared();
  let out = 0;
  try {
    for (const [name, url, outRe] of LOGIN_CHECKS) {
      const page = await shared.newPage();
      try {
        await page.goto(url, { waitUntil: 'domcontentloaded' }).catch(() => {});
        await page.waitForTimeout(6000);
        const final = await page.currentUrl();
        const signedOut = outRe.test(final);
        if (signedOut) out = 1;
        console.log(`${name}: ${signedOut ? 'SIGNED OUT' : 'signed in'} ${final}`);
      } finally {
        await page.close().catch(() => {});
      }
    }
  } finally {
    await shared.close();
  }
  return out;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (args.command === 'pair') return doPair();
  if (args.command === 'check-login') return checkLogin();
  if (!args.file) throw new Error('usage: reel-publish <post.json> [--only a,b] [--dry-run] [--yes]');

  const post = loadPost(args.file);
  const names = selectPlatforms(post, args.only);
  const runDir = path.join(HOME_DIR, 'runs', post.slug);
  const runLog = path.join(runDir, 'run.log');
  fs.mkdirSync(runDir, { recursive: true });
  const log = (msg) => {
    const line = `${new Date().toISOString()} ${msg}`;
    console.log(line);
    fs.appendFileSync(runLog, line + '\n');
  };

  if (!args.yes && !args.dryRun) {
    console.log(printPlan({ ...post, yes: false }, names));
    return 0;
  }

  const mode = args.dryRun ? 'dryrun' : 'publish';
  const dir = post.dir;
  const results = readResults(dir);
  // Dry-run never writes results.json: a rehearsal must not mark a platform ok.
  const scratch = {};
  const todo = mode === 'publish' ? pendingPlatforms(results, names) : names;
  for (const n of names) if (!todo.includes(n)) log(`${n}: already ok, skipping`);
  log(`${mode} ${post.slug}: ${todo.join(', ') || 'nothing to do'}`);

  const shared = makeShared();
  let failed = 0;
  for (const name of todo) {
    const adapter = (await import(`./adapters/${name}.mjs`)).default;
    const platform = post.platforms[name];
    const ctx = {
      post, platform, mode, runDir, log,
      results: { ...results, ...scratch },
      newPage: shared.newPage,
    };
    try {
      log(`${name}: start`);
      const out = await adapter.run(ctx);
      if (out.note) log(`${name}: note: ${out.note}`);
      const outcome = { ok: true, url: out.url, error: null };
      if (mode === 'publish') recordResult(dir, name, outcome);
      else scratch[name] = outcome;
      log(`${name}: ok${out.url ? ' ' + out.url : ''}`);
    } catch (e) {
      failed++;
      const outcome = { ok: false, url: null, error: e.message.split('\n')[0] };
      if (mode === 'publish') recordResult(dir, name, outcome);
      else scratch[name] = outcome;
      log(`${name}: FAILED: ${e.message}`);
    }
  }
  await shared.close();
  log(`done: ${todo.length - failed} ok, ${failed} failed`);
  return failed ? 1 : 0;
}

main().then((code) => { process.exitCode = code; }).catch((e) => {
  console.error(e.message);
  process.exitCode = e.message.startsWith('invalid post.json') || e.message.startsWith('unknown platform') || e.message.startsWith('not in post.json') ? 2 : 1;
});
