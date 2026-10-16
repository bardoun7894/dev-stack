#!/usr/bin/env node
// reel-publish <post.json> [--only a,b] [--dry-run] [--yes]
//        reel-publish login
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { loadPost, selectPlatforms, pendingPlatforms, scheduleParts } from './lib/post.mjs';
import { readResults, recordResult } from './lib/results.mjs';

const HOME_DIR = path.join(os.homedir(), '.reel-publish');
const PROFILE = path.join(HOME_DIR, 'chrome-profile');
const BROWSER_PLATFORMS = new Set(['tiktok', 'facebook_page', 'facebook_profile', 'linkedin', 'drive']);
const LOGIN_URLS = ['https://www.tiktok.com/', 'https://www.facebook.com/', 'https://business.facebook.com/',
  'https://www.linkedin.com/', 'https://drive.google.com/drive/u/1/'];

function parseArgs(argv) {
  const args = { file: null, only: null, dryRun: false, yes: false, login: false };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--only') args.only = (argv[++i] || '').split(',').filter(Boolean);
    else if (a === '--dry-run') args.dryRun = true;
    else if (a === '--yes') args.yes = true;
    else if (a === 'login') args.login = true;
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

async function launchContext() {
  const { chromium } = await import('playwright');
  fs.mkdirSync(PROFILE, { recursive: true });
  return chromium.launchPersistentContext(PROFILE, {
    channel: 'chrome', headless: false, viewport: { width: 1440, height: 900 },
  });
}

async function login() {
  const context = await launchContext();
  for (const url of LOGIN_URLS) {
    const page = context.pages()[0] || (await context.newPage());
    await page.goto(url).catch(() => {});
    if (context.pages().length < LOGIN_URLS.length) await context.newPage();
  }
  console.log('Sign in by hand, then close the browser window. Credentials are never typed by this tool.');
  await new Promise((resolve) => context.on('close', resolve));
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (args.login) return login();
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

  let context = null;
  const shared = {
    async newPage() {
      if (!context) context = await launchContext();
      return context.newPage();
    },
  };
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
  if (context) await context.close().catch(() => {});
  log(`done: ${todo.length - failed} ok, ${failed} failed`);
  return failed ? 1 : 0;
}

main().then((code) => { process.exitCode = code; }).catch((e) => {
  console.error(e.message);
  process.exitCode = e.message.startsWith('invalid post.json') || e.message.startsWith('unknown platform') || e.message.startsWith('not in post.json') ? 2 : 1;
});
