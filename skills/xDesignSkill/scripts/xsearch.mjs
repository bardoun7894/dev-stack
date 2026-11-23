// xsearch.mjs — X's own search, through a logged-in browser profile that belongs to this
// skill only (~/.config/xdesign/chrome-profile, mode 700, outside the skill folder).
//
// `xdesign login` opens a visible Chrome on that profile; the user types the password and
// 2FA there, so no script ever sees or stores a password. `find` then reads the X search
// page headless with the same profile. When there is no login, or X shows a login wall,
// or playwright-core is missing, it returns { ok: false, note } and find goes on without it.
// It never starts a login by itself: other agents run find unattended.

import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { extractPostRefs, ideaTerms, slugify, GENERIC } from './lib.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
export const PROFILE = process.env.XDESIGN_PROFILE || path.join(os.homedir(), '.config', 'xdesign', 'chrome-profile');
const CACHE = process.env.XDESIGN_CACHE || path.join(os.homedir(), '.cache', 'xdesign');
const SEARCH_TTL_MS = 24 * 3600e3, LOGIN_WAIT_MS = 5 * 60e3, SCROLLS = 3;
const ARGS = ['--disable-blink-features=AutomationControlled', '--disable-dev-shm-usage', '--no-first-run', '--no-default-browser-check'];

function findBrowser() {
  const env = process.env.XDESIGN_BROWSER || process.env.CHROME_PATH;
  const mac = ['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', '/Applications/Chromium.app/Contents/MacOS/Chromium', '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge', '/Applications/Brave Browser.app/Contents/MacOS/Brave Browser'];
  // Snap Chromium (Ubuntu's /usr/bin/chromium-browser too) cannot write a profile under ~/.config: last.
  const linux = ['/usr/bin/google-chrome', '/usr/bin/google-chrome-stable', '/usr/bin/chromium', '/usr/bin/chromium-browser', '/snap/bin/chromium'];
  return [env, ...(process.platform === 'darwin' ? mac : linux)].filter(Boolean).find((p) => fs.existsSync(p)) || null;
}

// playwright-core only (no browser download), installed next to this file on first use.
async function loadPlaywright({ install = false } = {}) {
  try { return await import('playwright-core'); } catch { /* not installed yet */ }
  if (!install) return null;
  console.error('xdesign: installing playwright-core into ' + HERE + ' (one time, no browser download)');
  const r = spawnSync('npm', ['install', '--silent', '--no-audit', '--no-fund'], { cwd: HERE, stdio: 'inherit' });
  if (r.status !== 0) return null;
  try { return await import('playwright-core'); } catch { return null; }
}

const hasAuth = async (ctx) => (await ctx.cookies('https://x.com')).some((c) => c.name === 'auth_token' && c.value);

async function openProfile(pw, headless) {
  const exe = findBrowser();
  if (!exe) throw new Error('no Chrome/Chromium found; set XDESIGN_BROWSER');
  fs.mkdirSync(PROFILE, { recursive: true, mode: 0o700 });
  fs.chmodSync(path.dirname(PROFILE), 0o700);
  return pw.chromium.launchPersistentContext(PROFILE, { headless, executablePath: exe, args: ARGS, viewport: { width: 1280, height: 900 }, locale: 'en-US' });
}

// Visible window; waits until the X session cookie exists, then closes. Never prints a value.
export async function login() {
  const pw = await loadPlaywright({ install: true });
  if (!pw) throw new Error('playwright-core could not be installed');
  const ctx = await openProfile(pw, false);
  try {
    if (await hasAuth(ctx)) return { ok: true, already: true };
    const page = ctx.pages()[0] || await ctx.newPage();
    await page.goto('https://x.com/i/flow/login', { waitUntil: 'domcontentloaded', timeout: 60000 }).catch(() => {});
    console.error('xdesign: log in to X in the Chrome window that opened (waiting up to 5 minutes)');
    const end = Date.now() + LOGIN_WAIT_MS;
    while (Date.now() < end) {
      if (await hasAuth(ctx)) { await new Promise((r) => setTimeout(r, 2000)); return { ok: true }; }
      if (!ctx.pages().length) break; // the user closed the window
      await new Promise((r) => setTimeout(r, 2000));
    }
    return { ok: false };
  } finally { await ctx.close().catch(() => {}); }
}

// Move the X session to a machine with no screen (a server): `xdesign session export | ssh host
// xdesign session import`. Only x.com / twitter.com cookies travel, through the pipe; nothing
// is written outside the two profiles. The caller refuses to print them to a terminal.
const isX = (c) => /(^|\.)(x|twitter)\.com$/.test(String(c.domain).replace(/^\./, ''));
export async function exportSession() {
  if (!fs.existsSync(PROFILE)) throw new Error('no login profile here (run: xdesign login)');
  const pw = await loadPlaywright();
  if (!pw) throw new Error('playwright-core not installed (run: xdesign login)');
  const ctx = await openProfile(pw, true);
  try {
    if (!(await hasAuth(ctx))) throw new Error('profile has no X session (run: xdesign login)');
    return { cookies: (await ctx.cookies()).filter(isX) };
  } finally { await ctx.close().catch(() => {}); }
}
export async function importSession(data) {
  const cookies = (data?.cookies || []).filter(isX);
  if (!cookies.some((c) => c.name === 'auth_token' && c.value)) throw new Error('input has no X session cookie');
  const pw = await loadPlaywright({ install: true });
  if (!pw) throw new Error('playwright-core could not be installed');
  const ctx = await openProfile(pw, true);
  try { await ctx.addCookies(cookies); return { ok: await hasAuth(ctx), count: cookies.length }; }
  finally { await ctx.close().catch(() => {}); }
}

export async function logout() {
  if (fs.existsSync(PROFILE)) fs.rmSync(PROFILE, { recursive: true, force: true });
}

// The X search query for an idea. X needs every word of a query in the post, so a long idea
// finds nothing: ask for any one subject word plus the screen type instead. Then: posts that
// call themselves UI/UX work (X search otherwise returns news and data-course projects that
// share the words), media only, and a likes floor so the top results are liked designs.
export function xQuery(idea, minFaves = 20) {
  const { subject, types } = ideaTerms(idea);
  const specific = subject.filter((w) => !GENERIC.has(w));
  const words = (specific.length ? specific : subject).slice(0, 4);
  const any = words.length > 1 ? `(${words.join(' OR ')})` : words[0] || '';
  const base = [any, types[0] || ''].filter(Boolean).join(' ') || String(idea).trim();
  const design = /\b(ui|ux|figma)\b/i.test(String(idea)) && !types.length ? '' : ' (UI OR UX OR Figma)';
  return `${base}${design} filter:media${minFaves > 0 ? ` min_faves:${minFaves}` : ''} -filter:replies`;
}

export async function status() {
  if (!fs.existsSync(PROFILE)) return { login: false, note: 'no login profile yet (run: xdesign login)' };
  const pw = await loadPlaywright();
  if (!pw) return { login: false, note: 'playwright-core not installed (run: xdesign login)' };
  const ctx = await openProfile(pw, true).catch((e) => ({ error: e.message }));
  if (ctx.error) return { login: false, note: ctx.error };
  try { return (await hasAuth(ctx)) ? { login: true } : { login: false, note: 'profile has no X session (run: xdesign login)' }; }
  finally { await ctx.close().catch(() => {}); }
}

// Returns { ok, refs: [{id, handle}], note }. Top tab first (best received), then Latest.
export async function searchX(idea, { minFaves = 20 } = {}) {
  const q = xQuery(idea, minFaves);
  const file = path.join(CACHE, 'xsearch', `${slugify(q)}.json`);
  try { const hit = JSON.parse(fs.readFileSync(file, 'utf8')); if (Date.now() - hit.at < SEARCH_TTL_MS) return { ok: true, refs: hit.refs, note: `x search "${q}": ${hit.refs.length} links (saved today)` }; } catch { /* no cache */ }
  if (!fs.existsSync(PROFILE)) return { ok: false, refs: [], note: 'x search: skipped, no login (run: xdesign login)' };
  const pw = await loadPlaywright();
  if (!pw) return { ok: false, refs: [], note: 'x search: skipped, playwright-core not installed (run: xdesign login)' };
  let ctx;
  try {
    ctx = await openProfile(pw, true);
    if (!(await hasAuth(ctx))) return { ok: false, refs: [], note: 'x search: skipped, the X session is gone (run: xdesign login)' };
    const page = ctx.pages()[0] || await ctx.newPage();
    const refs = new Map(); const tabs = [];
    for (const tab of ['top', 'live']) {
      await page.goto(`https://x.com/search?q=${encodeURIComponent(q)}&src=typed_query&f=${tab}`, { waitUntil: 'domcontentloaded', timeout: 45000 });
      const got = await page.waitForSelector('article [href*="/status/"]', { timeout: 20000 }).then(() => true).catch(() => false);
      if (!got) {
        const wall = /\/login|\/i\/flow/.test(page.url()) || await page.locator('a[href="/login"], [data-testid="loginButton"]').count() > 0;
        tabs.push(`${tab}: ${wall ? 'login wall' : '0 links'}`);
        if (wall) return { ok: false, refs: [], note: `x search "${q}": X showed a login wall (run: xdesign login)` };
        continue;
      }
      for (let i = 0; i < SCROLLS; i++) {
        const html = await page.$$eval('article a[href*="/status/"]', (as) => as.map((a) => a.href).join('\n'));
        for (const r of extractPostRefs(html)) if (!refs.has(r.id)) refs.set(r.id, r);
        await page.mouse.wheel(0, 2400);
        await page.waitForTimeout(1500);
      }
      tabs.push(`${tab}: ${refs.size} links so far`);
    }
    const list = [...refs.values()];
    if (list.length) { fs.mkdirSync(path.dirname(file), { recursive: true }); fs.writeFileSync(file, JSON.stringify({ at: Date.now(), refs: list })); }
    return { ok: true, refs: list, note: `x search "${q}": ${list.length} links (${tabs.join(', ')})` };
  } catch (e) {
    return { ok: false, refs: [], note: `x search: failed (${e.message.split('\n')[0]})` };
  } finally { if (ctx) await ctx.close().catch(() => {}); }
}
