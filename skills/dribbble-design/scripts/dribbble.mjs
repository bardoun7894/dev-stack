#!/usr/bin/env node
// dribbble.mjs — search Dribbble, download reference images, write a manifest.
//
//   node dribbble.mjs search "fashion app" [--type mobile|web-design|product-design|all]
//                            [--sort popular|recent] [--pages 1..5] [--limit 24] [--json]
//   node dribbble.mjs fetch  "fashion app" [same flags] [--out DIR] [--full] [--min-likes N]
//   node dribbble.mjs download <shot-url|id> [...]   [--out DIR] [--full]
//   node dribbble.mjs doctor                          (browser + deps check)
//
// Dribbble's public API has no search endpoint and the site sits behind an AWS WAF
// JS challenge, so this drives a real headless Chromium (playwright-core + the
// system Chrome/Chromium; no browser download). Reference use only — see SKILL.md.

import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36';
const MAX_PAGES = 5, MAX_DOWNLOADS = 40, PAGE_DELAY_MS = 900;
const TYPES = { all: '', mobile: 'mobile', web: 'web-design', 'web-design': 'web-design', product: 'product-design', 'product-design': 'product-design', branding: 'branding', animation: 'animation', typography: 'typography', illustration: 'illustration' };

// ── args ────────────────────────────────────────────────────────────────
const argv = process.argv.slice(2);
const cmd = argv.shift();
const flags = {}; const pos = [];
for (let i = 0; i < argv.length; i++) {
  const a = argv[i];
  if (a.startsWith('--')) { const k = a.slice(2); const v = argv[i + 1]; if (v !== undefined && !v.startsWith('--')) { flags[k] = v; i++; } else flags[k] = true; }
  else pos.push(a);
}
const opt = {
  type: TYPES[flags.type ?? 'all'] ?? '', sort: flags.sort === 'recent' ? 'recent' : 'popular',
  pages: Math.min(MAX_PAGES, Math.max(1, parseInt(flags.pages ?? '1', 10) || 1)),
  limit: Math.min(MAX_DOWNLOADS, Math.max(1, parseInt(flags.limit ?? '24', 10) || 24)),
  json: !!flags.json, full: !!flags.full, out: flags.out, minLikes: parseInt(flags['min-likes'] ?? '0', 10) || 0,
  headful: !!flags.headful,
};
if (flags.type && TYPES[flags.type] === undefined) die(`unknown --type ${flags.type}; one of ${Object.keys(TYPES).join(', ')}`);

function die(msg, code = 1) { console.error('dribbble: ' + msg); process.exit(code); }
const log = (...a) => { if (!opt.json) console.error(...a); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
const slugify = s => s.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 60) || 'shots';

// ── deps / browser ──────────────────────────────────────────────────────
async function loadPlaywright() {
  try { return await import('playwright-core'); }
  catch {
    log('installing playwright-core into', HERE, '(one-time, no browser download)');
    const r = spawnSync('npm', ['install', '--silent', '--no-audit', '--no-fund'], { cwd: HERE, stdio: 'inherit' });
    if (r.status !== 0) die('npm install failed in ' + HERE);
    return await import('playwright-core');
  }
}
function findBrowser() {
  const env = process.env.DRIBBBLE_BROWSER || process.env.CHROME_PATH;
  const mac = ['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', '/Applications/Chromium.app/Contents/MacOS/Chromium', '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge', '/Applications/Brave Browser.app/Contents/MacOS/Brave Browser'];
  const linux = ['/usr/bin/chromium-browser', '/usr/bin/chromium', '/usr/bin/google-chrome', '/usr/bin/google-chrome-stable', '/snap/bin/chromium', '/usr/bin/microsoft-edge'];
  const cands = [env, ...(process.platform === 'darwin' ? mac : linux)].filter(Boolean);
  const found = cands.find(p => fs.existsSync(p));
  if (found) return found;
  // playwright cache (any version)
  const cache = process.platform === 'darwin' ? path.join(os.homedir(), 'Library/Caches/ms-playwright') : path.join(os.homedir(), '.cache/ms-playwright');
  if (fs.existsSync(cache)) for (const d of fs.readdirSync(cache)) {
    for (const rel of ['chrome-linux/chrome', 'chrome-mac-arm64/Chromium.app/Contents/MacOS/Chromium', 'chrome-mac/Chromium.app/Contents/MacOS/Chromium', 'chrome-headless-shell-linux64/chrome-headless-shell', 'chrome-headless-shell-mac-arm64/chrome-headless-shell']) {
      const p = path.join(cache, d, rel); if (fs.existsSync(p)) return p;
    }
  }
  return null;
}
async function openBrowser() {
  const pw = await loadPlaywright();
  const exe = findBrowser();
  if (!exe) die('no Chrome/Chromium found. Install Google Chrome, or set DRIBBBLE_BROWSER=/path/to/chrome');
  const browser = await pw.chromium.launch({ headless: !opt.headful, executablePath: exe, args: ['--no-sandbox', '--disable-blink-features=AutomationControlled', '--disable-dev-shm-usage'] });
  const ctx = await browser.newContext({ userAgent: UA, viewport: { width: 1440, height: 900 }, locale: 'en-US' });
  return { browser, ctx, exe };
}

// ── scraping ────────────────────────────────────────────────────────────
function searchUrl(q, page) {
  const seg = opt.type ? `/${opt.type}` : '';
  const u = new URL(`https://dribbble.com/search/shots/${opt.sort}${seg}`);
  u.searchParams.set('q', q); if (page > 1) u.searchParams.set('page', String(page));
  return u.toString();
}
const stripParams = u => u ? u.split('?')[0] : u;
function upsize(u) { // request a large webp render from the CDN (originals are often 4k+)
  if (!u) return u; const base = stripParams(u); return `${base}?format=webp&resize=1600x1200&vertical=center`;
}
async function scrapeCards(page) {
  return page.evaluate(() => {
    const seen = new Map();
    document.querySelectorAll('li.shot-thumbnail, .shot-thumbnail-base').forEach(li => {
      const a = li.querySelector('a[href^="/shots/"]'); if (!a) return;
      const href = a.getAttribute('href').split('?')[0]; if (seen.has(href)) return;
      const img = li.querySelector('img');
      const srcset = (img?.getAttribute('srcset') || img?.getAttribute('data-srcset') || '');
      const largest = srcset.split(',').map(s => s.trim().split(' ')[0]).filter(Boolean).pop();
      const likes = li.querySelector('.js-shot-likes-count, [class*="likes-count"]')?.textContent?.replace(/[^\d.k]/gi, '') || '';
      const views = li.querySelector('.js-shot-views-count, [class*="views-count"]')?.textContent?.replace(/[^\d.k]/gi, '') || '';
      seen.set(href, {
        id: href.match(/\/shots\/(\d+)/)?.[1], slug: href.replace('/shots/', ''), url: 'https://dribbble.com' + href,
        title: (img?.getAttribute('alt') || a.getAttribute('title') || '').trim(),
        author: li.querySelector('.display-name')?.textContent?.trim() || li.querySelector('a[href^="/"][rel="contact"]')?.textContent?.trim() || '',
        author_url: (() => { const p = li.querySelector('a.hoverable.url, .user-information a[href^="/"]'); return p ? 'https://dribbble.com' + p.getAttribute('href') : ''; })(),
        thumb: img?.getAttribute('src') || img?.getAttribute('data-src') || '', image: largest || img?.getAttribute('src') || '',
        likes, views, video: !!li.querySelector('video, [data-video-teaser-small], .shot-thumbnail-video'),
      });
    });
    return [...seen.values()];
  });
}
async function search(ctx, q) {
  const page = await ctx.newPage(); const all = new Map();
  for (let p = 1; p <= opt.pages; p++) {
    const url = searchUrl(q, p); log(`→ ${url}`);
    const resp = await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 60000 });
    try { await page.waitForSelector('li.shot-thumbnail, .shot-thumbnail-base', { timeout: 30000 }); }
    catch { log(`  no shots on page ${p} (status ${resp?.status()}, title "${await page.title()}")`); break; }
    // trigger lazy images
    await page.mouse.wheel(0, 4000); await sleep(600); await page.mouse.wheel(0, 4000); await sleep(400);
    // like/view counts are filled in asynchronously after the cards mount
    await page.waitForFunction(() => document.querySelector('.js-shot-likes-count, [class*="likes-count"]')?.textContent?.trim(), null, { timeout: 5000 }).catch(() => {});
    const cards = await scrapeCards(page);
    cards.forEach(c => { if (!all.has(c.url)) all.set(c.url, c); });
    log(`  page ${p}: ${cards.length} cards (total ${all.size})`);
    if (all.size >= opt.limit || cards.length === 0) break;
    await sleep(PAGE_DELAY_MS);
  }
  await page.close();
  return [...all.values()].map(c => ({ ...c, original: stripParams(c.image), image: upsize(c.image), thumb: c.thumb, query: q })).slice(0, opt.limit);
}
async function shotMedia(ctx, shot) { // all media on the shot page (multi-screen case studies)
  const page = await ctx.newPage();
  try {
    await page.goto(shot.url, { waitUntil: 'domcontentloaded', timeout: 60000 });
    await page.waitForSelector('img[src*="cdn.dribbble.com/userupload"], video[src*="cdn.dribbble.com"]', { timeout: 30000 }).catch(() => {});
    for (let i = 0; i < 6; i++) { await page.mouse.wheel(0, 2500); await sleep(350); }
    const media = await page.evaluate(() => {
      const out = new Set();
      document.querySelectorAll('img[src*="cdn.dribbble.com/userupload"], img[srcset*="cdn.dribbble.com/userupload"], img[data-src*="cdn.dribbble.com/userupload"]').forEach(im => {
        if (im.closest('header, nav, footer, .shot-thumbnail, [class*="related"], [class*="more-by"]')) return;
        const ss = im.getAttribute('srcset') || im.getAttribute('data-srcset') || '';
        const largest = ss.split(',').map(s => s.trim().split(' ')[0]).filter(Boolean).pop();
        out.add((largest || im.getAttribute('src') || im.getAttribute('data-src')).split('?')[0]);
      });
      const desc = document.querySelector('.shot-description, [class*="shot-description"], .description')?.innerText?.trim().slice(0, 600) || '';
      const tags = [...document.querySelectorAll('a[href^="/tags/"]')].map(a => a.textContent.trim()).filter(Boolean).slice(0, 20);
      const title = document.querySelector('h1')?.textContent?.trim() || '';
      const author = document.querySelector('.shot-user-details a[href^="/"], [class*="user-details"] a[href^="/"], h2 a[href^="/"]')?.textContent?.trim() || '';
      return { media: [...out], desc, tags, title, author };
    });
    return media;
  } finally { await page.close(); }
}

// ── download ────────────────────────────────────────────────────────────
function projectRoot() {
  let d = process.cwd(); const home = os.homedir();
  while (d !== '/' && d !== home) { if (fs.existsSync(path.join(d, '.git')) || fs.existsSync(path.join(d, '.claude'))) return d; d = path.dirname(d); }
  return process.cwd();
}
function defaultOut(q) { return path.join(projectRoot(), 'design', 'inspiration', `${new Date().toISOString().slice(0, 10)}-${slugify(q)}`); }
async function fetchTo(url, file, referer) {
  const r = await fetch(url, { headers: { 'User-Agent': UA, Referer: referer || 'https://dribbble.com/', Accept: 'image/avif,image/webp,image/*,*/*' } });
  if (!r.ok) throw new Error(`HTTP ${r.status} ${url}`);
  const ct = r.headers.get('content-type') || '';
  const ext = ct.includes('webp') ? 'webp' : ct.includes('png') ? 'png' : ct.includes('gif') ? 'gif' : ct.includes('mp4') ? 'mp4' : 'jpg';
  const out = file.replace(/\.EXT$/, '.' + ext);
  fs.writeFileSync(out, Buffer.from(await r.arrayBuffer()));
  return { out, bytes: fs.statSync(out).size, type: ct };
}
const LICENSE_NOTE = 'Reference/inspiration only. Images remain the property of their authors; do not redistribute or ship them as product assets.';
// Several queries can share one folder (a research packet): merge into the existing
// manifest instead of overwriting it, keep numbering monotonic, skip shots already saved.
function loadManifest(outDir) {
  const f = path.join(outDir, 'manifest.json');
  if (!fs.existsSync(f)) return { queries: [], fetched_at: new Date().toISOString(), source: 'https://dribbble.com', license_note: LICENSE_NOTE, shots: [] };
  try {
    const m = JSON.parse(fs.readFileSync(f, 'utf8'));
    m.queries = m.queries || (m.query ? [m.query] : []); delete m.query;
    m.shots = m.shots || []; m.license_note = LICENSE_NOTE;
    return m;
  } catch { return { queries: [], fetched_at: new Date().toISOString(), source: 'https://dribbble.com', license_note: LICENSE_NOTE, shots: [] }; }
}
async function download(ctx, shots, outDir, q) {
  fs.mkdirSync(outDir, { recursive: true });
  const manifest = loadManifest(outDir);
  if (q && !manifest.queries.includes(q)) manifest.queries.push(q);
  manifest.updated_at = new Date().toISOString();
  const have = new Set(manifest.shots.map(s => s.url));
  let n = manifest.shots.reduce((mx, s) => Math.max(mx, parseInt(s.n, 10) || 0), 0);
  for (const s of shots.slice(0, MAX_DOWNLOADS)) {
    if (have.has(s.url)) { log(`  · already have ${s.slug}`); continue; }
    n++; const base = `${String(n).padStart(2, '0')}-${slugify(s.slug || s.id || 'shot')}`;
    const entry = { n, ...s, files: [] };
    try {
      let urls = [s.image || upsize(s.original)];
      if (opt.full) {
        const m = await shotMedia(ctx, s);
        if (m.title) entry.title = m.title; if (m.author) entry.author = m.author;
        entry.description = m.desc; entry.tags = m.tags;
        if (m.media.length) urls = m.media.map(upsize);
      }
      let k = 0;
      for (const u of urls.slice(0, 12)) {
        k++; const f = path.join(outDir, urls.length > 1 ? `${base}-${String(k).padStart(2, '0')}.EXT` : `${base}.EXT`);
        const r = await fetchTo(u, f, s.url); entry.files.push({ path: path.relative(outDir, r.out), bytes: r.bytes, src: u });
        log(`  ✓ ${path.basename(r.out)} (${(r.bytes / 1024).toFixed(0)} KB)`);
        await sleep(250);
      }
    } catch (e) { entry.error = String(e.message || e); log(`  ✗ ${base}: ${entry.error}`); }
    manifest.shots.push(entry);
  }
  fs.writeFileSync(path.join(outDir, 'manifest.json'), JSON.stringify(manifest, null, 2));
  const title = manifest.queries.length ? manifest.queries.join(' · ') : 'selected shots';
  const md = ['# Dribbble references — ' + title, '', `Fetched ${manifest.updated_at}. ${manifest.license_note}`, '', '| # | Shot | Author | ♥ / 👁 | Query | Files |', '|---|---|---|---|---|---|',
    ...manifest.shots.map(s => `| ${s.n || ''} | [${(s.title || s.slug).split(/\s{2,}| (?=[a-z]+ [a-z]+ [a-z]+ [a-z]+)/)[0].slice(0, 70)}](${s.url}) | ${s.author || ''} | ${s.likes || s.views || ''} | ${s.query || ''} | ${s.files.map(f => `\`${f.path}\``).join(' ') || s.error || ''} |`), ''].join('\n');
  fs.writeFileSync(path.join(outDir, 'README.md'), md);
  return manifest;
}

// ── output ──────────────────────────────────────────────────────────────
function printTable(shots) {
  if (opt.json) { console.log(JSON.stringify(shots, null, 2)); return; }
  shots.forEach((s, i) => console.log(`${String(i + 1).padStart(2)}. ${(s.title || s.slug).slice(0, 80)}\n    ${s.url}\n    by ${s.author || '?'}${s.likes ? ' · ♥ ' + s.likes : ''}${s.views ? ' · 👁 ' + s.views : ''}${s.video ? ' · video' : ''}\n    img ${s.image}`));
}
function parseShotArg(a) {
  const m = a.match(/(\d{5,})(?:-([\w-]+))?/); if (!m) die(`not a shot url/id: ${a}`);
  return { id: m[1], slug: a.includes('/shots/') ? a.split('/shots/')[1].split(/[?#]/)[0] : (m[2] ? `${m[1]}-${m[2]}` : m[1]), url: `https://dribbble.com/shots/${m[1]}${m[2] ? '-' + m[2] : ''}`, title: '', author: '', image: '', original: '' };
}

// ── main ────────────────────────────────────────────────────────────────
(async () => {
  if (!cmd || cmd === '--help' || cmd === '-h') { console.log(fs.readFileSync(fileURLToPath(import.meta.url), 'utf8').split('\n').slice(1, 12).map(l => l.replace(/^\/\/ ?/, '')).join('\n')); process.exit(0); }
  if (cmd === 'doctor') {
    const exe = findBrowser(); console.log('browser :', exe || 'NOT FOUND (set DRIBBBLE_BROWSER)');
    console.log('node    :', process.version);
    let pwv = 'missing'; try { pwv = JSON.parse(fs.readFileSync(path.join(HERE, 'node_modules/playwright-core/package.json'))).version; } catch {}
    console.log('playwright-core :', pwv, pwv === 'missing' ? '(auto-installs on first run)' : '');
    console.log('out dir :', defaultOut('example'));
    process.exit(exe ? 0 : 1);
  }
  if (!['search', 'fetch', 'download'].includes(cmd)) die(`unknown command ${cmd}. Use search | fetch | download | doctor`);
  const { browser, ctx, exe } = await openBrowser(); log('browser:', exe);
  try {
    if (cmd === 'search') { const q = pos.join(' '); if (!q) die('search needs a query'); printTable(await search(ctx, q)); }
    else if (cmd === 'fetch') {
      const q = pos.join(' '); if (!q) die('fetch needs a query');
      let shots = await search(ctx, q);
      // like counts are hidden for logged-out visitors on many cards; fall back to views
      const num = v => (parseFloat(v) || 0) * (/k/i.test(v) ? 1000 : 1);
      if (opt.minLikes) shots = shots.filter(s => Math.max(num(s.likes), num(s.views)) >= opt.minLikes);
      const outDir = opt.out ? path.resolve(opt.out) : defaultOut(q);
      log(`downloading ${Math.min(shots.length, opt.limit)} shots → ${outDir}`);
      const m = await download(ctx, shots.slice(0, opt.limit), outDir, q);
      if (opt.json) console.log(JSON.stringify(m, null, 2)); else console.log(`${m.shots.filter(s => s.files.length).length}/${m.shots.length} shots saved → ${outDir}\nmanifest: ${path.join(outDir, 'manifest.json')}`);
    } else {
      if (!pos.length) die('download needs shot urls or ids');
      const shots = pos.map(parseShotArg); opt.full = true;
      const outDir = opt.out ? path.resolve(opt.out) : defaultOut('shots-' + shots.map(s => s.id).join('-').slice(0, 40));
      const m = await download(ctx, shots, outDir, '');
      if (opt.json) console.log(JSON.stringify(m, null, 2)); else console.log(`${m.shots.filter(s => s.files.length).length}/${m.shots.length} shots saved → ${outDir}`);
    }
  } finally { await browser.close(); }
})().catch(e => die(e.stack || String(e)));
