#!/usr/bin/env node
// xdesign.mjs — pull UI/UX design references from the latest X (Twitter) posts.
//
//   node xdesign.mjs find     "<idea>" [--handles a,b] [--days N] [--limit N] [--all] [--json]
//   node xdesign.mjs fetch    "<idea>" [same flags] [--out DIR] [--no-frames]
//   node xdesign.mjs latest   <handle>... [--limit N] [--json]
//   node xdesign.mjs download <post-url|id>... [--out DIR] [--subject "<text>"] [--no-frames]
//   node xdesign.mjs handles  [list | add <handle>... | rm <handle>... | check [<handle>...]]
//   node xdesign.mjs doctor
//
// X search needs a login, so there is no search call here. `find` reads the newest media
// posts of a watchlist of designer accounts (public FxTwitter API, no key, no login) and
// ranks them by closeness to the idea. A post found any other way (pasted link, web search)
// goes through `download`. Images are saved at original size, cut into tiles when large,
// and sampled for their real colors; videos are saved and cut into frames with ffmpeg.
// Reference use only — see SKILL.md.

import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const API = process.env.XDESIGN_API || 'https://api.fxtwitter.com';
const UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36';
const SEED_FILE = path.join(HERE, '..', 'references', 'designers.txt');
const USER_FILE = process.env.XDESIGN_HANDLES || path.join(os.homedir(), '.config', 'xdesign', 'handles.txt');
const MAX_HANDLES = 30, MAX_DOWNLOADS = 30, HANDLE_DELAY_MS = 900, MAX_VIDEO_MB = 80, MAX_VIDEO_SEC = 240;
const TILE_MIN_WIDTH = 2600; // wider than this, small labels are lost when the whole image is viewed at once

export * from './lib.mjs';
import { slugify, parsePostRef, cleanHandle, parseHandleList, normalizePost, ideaTerms, rankPosts, quantize } from './lib.mjs';

// ── cli plumbing ────────────────────────────────────────────────────────
const flags = {}; const pos = [];
let jsonOut = false;
function die(msg, code = 1) { console.error('xdesign: ' + msg); process.exit(code); }
const log = (...a) => { if (!jsonOut) console.error(...a); };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const hasBin = (b) => spawnSync(b, ['-version'], { stdio: 'ignore' }).status === 0;

async function getJson(url) {
  let res;
  try { res = await fetch(url, { headers: { 'user-agent': UA, accept: 'application/json' }, signal: AbortSignal.timeout(25000) }); }
  catch (e) { return { ok: false, status: 0, error: e.message }; }
  let body = null;
  try { body = await res.json(); } catch { /* not json */ }
  return { ok: res.ok, status: res.status, body };
}

// The API answers 404 or an empty list at random when its upstream throttles, and the two
// timeline endpoints fail independently. So: media, then statuses, then media again, with
// a growing wait. Only three misses in a row count as "no data".
async function timeline(handle, count = 40) {
  const tries = [['media', 0], ['statuses', 1200], ['media', 3000]];
  let last = '';
  for (const [ep, wait] of tries) {
    if (wait) await sleep(wait);
    const r = await getJson(`${API}/2/profile/${encodeURIComponent(handle)}/${ep}?count=${count}`);
    const posts = (r.body?.results || []).filter((t) => !t.reposted_by && !t.replying_to).map(normalizePost).filter((p) => p && p.media.length);
    if (r.ok && posts.length) return { handle, posts };
    last = r.ok ? 'empty answer' : `http ${r.status}${r.error ? ' ' + r.error : ''}`;
  }
  return { handle, error: `no data after 3 tries (${last}); the account may not exist, or the API is throttling: retry later`, posts: [] };
}

async function getPost(id, handle) {
  const r = await getJson(`${API}/${handle || 'i'}/status/${id}`);
  if (r.ok && r.body?.tweet) return normalizePost(r.body.tweet);
  const token = ((Number(id) / 1e15) * Math.PI).toString(36).replace(/(0+|\.)/g, '');
  const s = await getJson(`https://cdn.syndication.twimg.com/tweet-result?id=${id}&token=${token}`);
  if (s.ok && s.body?.id_str) return normalizePost(s.body);
  return null;
}

function loadHandles() {
  const read = (f) => (fs.existsSync(f) ? parseHandleList(fs.readFileSync(f, 'utf8')) : []);
  const all = [...read(USER_FILE), ...read(SEED_FILE)];
  return all.filter((h, i) => all.findIndex((x) => x.toLowerCase() === h.toLowerCase()) === i);
}

function projectRoot() {
  let dir = process.cwd();
  const home = os.homedir();
  while (dir !== path.dirname(dir)) {
    if (dir !== home && (fs.existsSync(path.join(dir, '.git')) || fs.existsSync(path.join(dir, '.claude')))) return dir;
    dir = path.dirname(dir);
  }
  return null;
}

function outDir(subject) {
  if (flags.out) return path.resolve(String(flags.out));
  const root = projectRoot();
  if (!root) die('no project root (.git or .claude) above the current folder; pass --out DIR');
  return path.join(root, 'design', 'inspiration', `${new Date().toISOString().slice(0, 10)}-x-${slugify(subject)}`);
}

async function saveUrl(url, file, maxMb = 0) {
  const res = await fetch(url, { headers: { 'user-agent': UA }, signal: AbortSignal.timeout(120000) });
  if (!res.ok) throw new Error(`http ${res.status} for ${url}`);
  const len = Number(res.headers.get('content-length') || 0);
  if (maxMb && len > maxMb * 1048576) throw new Error(`${(len / 1048576).toFixed(0)} MB is over the ${maxMb} MB cap`);
  fs.writeFileSync(file, Buffer.from(await res.arrayBuffer()));
  return fs.statSync(file).size;
}

function palette(file) {
  const r = spawnSync('ffmpeg', ['-v', 'error', '-i', file, '-frames:v', '1', '-vf', 'scale=200:150:flags=neighbor', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], { maxBuffer: 1 << 24 });
  return r.status === 0 && r.stdout?.length ? quantize(r.stdout) : [];
}

// 2 x 2 tiles with a small overlap, so text on a seam is whole in at least one tile.
function tiles(file, base) {
  const out = [];
  [['0', '0'], ['iw*0.46', '0'], ['0', 'ih*0.46'], ['iw*0.46', 'ih*0.46']].forEach(([x, y], i) => {
    const f = `${base}-t${i + 1}.jpg`;
    const r = spawnSync('ffmpeg', ['-v', 'error', '-y', '-i', file, '-vf', `crop=iw*0.54:ih*0.54:${x}:${y}`, '-q:v', '2', f]);
    if (r.status === 0) out.push(path.basename(f));
  });
  return out;
}

function videoFrames(file, base, duration) {
  let dur = duration;
  if (!dur) {
    const p = spawnSync('ffprobe', ['-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', file], { encoding: 'utf8' });
    dur = parseFloat(p.stdout) || 0;
  }
  if (!dur) return { frames: [], sheet: null, duration: null };
  const n = Math.max(6, Math.min(16, Math.round(dur / 1.5)));
  const fps = (n / dur).toFixed(4);
  spawnSync('ffmpeg', ['-v', 'error', '-y', '-i', file, '-vf', `fps=${fps},scale='min(1600,iw)':-2`, '-frames:v', String(n), '-q:v', '3', `${base}-f%02d.jpg`]);
  const sheet = `${base}-sheet.jpg`;
  const s = spawnSync('ffmpeg', ['-v', 'error', '-y', '-i', file, '-vf', `fps=${fps},scale=480:-2,tile=4x${Math.ceil(n / 4)}`, '-frames:v', '1', '-q:v', '3', sheet]);
  const dir = path.dirname(base), stem = path.basename(base) + '-f';
  const frames = fs.readdirSync(dir).filter((f) => f.startsWith(stem) && f.endsWith('.jpg')).sort();
  return { frames, sheet: s.status === 0 ? path.basename(sheet) : null, duration: +dur.toFixed(1) };
}

async function savePosts(posts, subject) {
  const dir = outDir(subject);
  fs.mkdirSync(dir, { recursive: true });
  const manifestFile = path.join(dir, 'manifest.json');
  const manifest = fs.existsSync(manifestFile) ? JSON.parse(fs.readFileSync(manifestFile, 'utf8')) : { source: 'x', subjects: [], posts: [] };
  if (!manifest.subjects.includes(subject)) manifest.subjects.push(subject);
  const ff = hasBin('ffmpeg');
  if (!ff) log('ffmpeg not found: no tiles, no colors, no video frames');
  let n = manifest.posts.reduce((m, p) => Math.max(m, p.n), 0);
  let added = 0;

  for (const post of posts.slice(0, MAX_DOWNLOADS)) {
    if (manifest.posts.some((p) => p.id === post.id)) { log(`skip ${post.id} (already saved)`); continue; }
    n++;
    const stem = `${String(n).padStart(2, '0')}-${post.handle}-${post.id}`;
    const entry = { n, id: post.id, url: post.url, handle: post.handle, author: post.author, text: post.text, created_at: post.created_at, likes: post.likes, views: post.views, bookmarks: post.bookmarks, rank: post.rank || null, media: [] };
    for (let k = 0; k < post.media.length; k++) {
      const m = post.media[k];
      const base = path.join(dir, post.media.length > 1 ? `${stem}-${k + 1}` : stem);
      try {
        if (m.type === 'photo') {
          const ext = (m.url.match(/\.(jpg|jpeg|png|webp)/i)?.[1] || 'jpg').toLowerCase();
          const file = `${base}.${ext}`;
          const bytes = await saveUrl(m.url, file);
          const item = { type: 'photo', file: path.basename(file), width: m.width, height: m.height, bytes, source: m.url };
          if (ff) {
            item.palette = palette(file);
            if ((m.width || 0) >= TILE_MIN_WIDTH) item.tiles = tiles(file, base);
          }
          entry.media.push(item);
        } else {
          if ((m.duration || 0) > MAX_VIDEO_SEC) throw new Error(`video is ${Math.round(m.duration)} s, over the ${MAX_VIDEO_SEC} s cap`);
          const file = `${base}.mp4`;
          const bytes = await saveUrl(m.url, file, MAX_VIDEO_MB);
          const item = { type: 'video', file: path.basename(file), width: m.width, height: m.height, bytes, source: m.url };
          if (ff && !flags['no-frames']) {
            Object.assign(item, videoFrames(file, base, m.duration));
            if (item.frames?.length) item.palette = palette(path.join(dir, item.frames[Math.floor(item.frames.length / 2)]));
          }
          fs.writeFileSync(path.join(dir, '.gitignore'), '*.mp4\n');
          entry.media.push(item);
        }
      } catch (e) {
        entry.media.push({ type: m.type, error: e.message, source: m.url });
        log(`  ${post.id} media ${k + 1}: ${e.message}`);
      }
    }
    manifest.posts.push(entry); added++;
    log(`saved ${stem}  ${entry.media.map((x) => x.error ? 'ERR' : x.type === 'photo' ? `${x.width}x${x.height}${x.tiles ? ' +' + x.tiles.length + ' tiles' : ''}` : `video ${x.duration ?? '?'}s ${x.frames?.length ?? 0} frames`).join(', ')}`);
  }

  manifest.generated = new Date().toISOString();
  fs.writeFileSync(manifestFile, JSON.stringify(manifest, null, 2) + '\n');
  fs.writeFileSync(path.join(dir, 'README.md'), readme(manifest));
  return { dir, added, total: manifest.posts.length };
}

function readme(manifest) {
  const rows = manifest.posts.map((p) => {
    const files = p.media.filter((m) => !m.error).map((m) => `\`${m.file}\`${m.tiles?.length ? ` (+${m.tiles.length} tiles)` : ''}${m.frames?.length ? ` (+${m.frames.length} frames, \`${m.sheet}\`)` : ''}`).join('<br>');
    const colors = (p.media.find((m) => m.palette?.length)?.palette || []).slice(0, 6).map((c) => `\`${c.hex}\` ${c.share}%`).join(' ');
    return `| ${p.n} | [${(p.text || '').replace(/[|\n]/g, ' ').slice(0, 70) || p.id}](${p.url}) | @${p.handle} | ${(p.created_at || '').slice(0, 10)} | ${p.likes ?? ''} / ${p.views ?? ''} | ${files} | ${colors} |`;
  });
  return `# X design references — ${manifest.subjects.join(' · ')}\n\nThird-party work, saved for reference only. Do not ship these files or copy a post one-to-one.\nSource of truth for authors, links and colors is \`manifest.json\`.\n\n| # | Post | Author | Date | Likes / views | Files | Main colors (share of pixels) |\n|---|---|---|---|---|---|---|\n${rows.join('\n')}\n`;
}

function printPosts(posts) {
  if (jsonOut) { console.log(JSON.stringify(posts, null, 2)); return; }
  if (!posts.length) { console.log('no posts'); return; }
  for (const p of posts) {
    const media = p.media.map((m) => m.type === 'photo' ? `photo ${m.width}x${m.height}` : `video ${Math.round(m.duration || 0)}s`).join(', ');
    const why = p.rank ? `score ${p.rank.score} [${[...p.rank.subjectHits, ...p.rank.typeHits.map((t) => 'type:' + t)].join(' ') || 'no word match'}]` : '';
    console.log(`${(p.created_at || '').slice(0, 10)}  @${p.handle}  ${p.text.replace(/\s+/g, ' ').slice(0, 80)}\n            ${p.url}\n            ${media} · likes ${p.likes ?? '?'} · views ${p.views ?? '?'} ${why ? '· ' + why : ''}`);
  }
}

async function collect(handles) {
  const posts = [];
  for (const h of handles.slice(0, MAX_HANDLES)) {
    const t = await timeline(h);
    if (t.error) log(`@${h}: ${t.error}`); else log(`@${h}: ${t.posts.length} media posts`);
    posts.push(...t.posts);
    await sleep(HANDLE_DELAY_MS);
  }
  return posts;
}

function pickHandles() {
  const list = flags.handles ? String(flags.handles).split(',').map(cleanHandle).filter(Boolean) : loadHandles();
  if (!list.length) die('no handles: pass --handles a,b or run `handles add <handle>`');
  if (list.length > MAX_HANDLES) log(`watchlist has ${list.length} handles, reading the first ${MAX_HANDLES}`);
  return list;
}

const limitOf = (dflt) => Math.min(MAX_DOWNLOADS, Math.max(1, parseInt(flags.limit ?? dflt, 10) || dflt));

// ── commands ────────────────────────────────────────────────────────────
async function cmdFind(save) {
  const idea = pos.join(' ').trim();
  if (!idea) die('give the idea, e.g. find "transport fleet dashboard"');
  const terms = ideaTerms(idea);
  log(`idea words: ${terms.subject.join(', ') || '(none)'} · screen type: ${terms.types.join(', ') || '(none)'}`);
  const ranked = rankPosts(await collect(pickHandles()), idea, { all: !!flags.all, days: parseInt(flags.days ?? '0', 10) || 0 }).slice(0, limitOf(save ? 6 : 12));
  if (!save) return printPosts(ranked);
  if (!ranked.length) die('no post matches the idea; widen it (add sibling words), add handles, or pass --all', 3);
  const r = await savePosts(ranked, idea);
  console.log(`${r.added} new post(s) saved, ${r.total} in folder\n${r.dir}`);
}

async function cmdLatest() {
  const handles = pos.map(cleanHandle).filter(Boolean);
  if (!handles.length) die('give at least one handle');
  const posts = (await collect(handles)).sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at)).slice(0, limitOf(12));
  printPosts(posts);
}

async function cmdDownload() {
  if (!pos.length) die('give at least one post URL or id');
  const posts = [];
  for (const ref of pos) {
    const p = parsePostRef(ref);
    if (!p) { log(`not a post URL or id: ${ref}`); continue; }
    const post = await getPost(p.id, p.handle);
    if (!post) { log(`could not read post ${p.id}`); continue; }
    if (!post.media.length) { log(`post ${p.id} has no image or video`); continue; }
    posts.push(post);
  }
  if (!posts.length) die('nothing to download', 3);
  const r = await savePosts(posts, String(flags.subject || posts[0].text || posts[0].id));
  console.log(`${r.added} new post(s) saved, ${r.total} in folder\n${r.dir}`);
}

async function cmdHandles() {
  const sub = pos.shift() || 'list';
  const user = fs.existsSync(USER_FILE) ? parseHandleList(fs.readFileSync(USER_FILE, 'utf8')) : [];
  if (sub === 'list') { console.log(loadHandles().join('\n')); return; }
  if (sub === 'check') {
    const list = pos.length ? pos.map(cleanHandle).filter(Boolean) : loadHandles();
    const uiWords = /\b(ui|ux|dashboard|app|website|landing|interface|figma|saas|design)\b/i;
    for (const h of list) {
      const t = await timeline(h);
      const ui = t.posts.filter((p) => uiWords.test(p.text)).length;
      const newest = t.posts[0]?.created_at?.slice(0, 10) || '-';
      console.log(`${t.error ? 'FAIL' : ui >= 3 ? 'ok  ' : 'weak'}  @${h}  media posts ${t.posts.length}  ui-titled ${ui}  newest ${newest}${t.error ? '  ' + t.error : ''}`);
      await sleep(HANDLE_DELAY_MS);
    }
    return;
  }
  const names = pos.map(cleanHandle).filter(Boolean);
  if (!names.length) die(`handles ${sub}: give at least one handle`);
  if (sub === 'add') {
    for (const h of names) {
      if (user.some((x) => x.toLowerCase() === h.toLowerCase())) { console.log(`@${h} already listed`); continue; }
      const t = await timeline(h);
      if (t.error || !t.posts.length) { console.log(`@${h} not added: ${t.error || 'no media posts'}`); continue; }
      user.unshift(h); console.log(`@${h} added (${t.posts.length} media posts, newest ${t.posts[0].created_at?.slice(0, 10)})`);
    }
  } else if (sub === 'rm') {
    for (const h of names) { const i = user.findIndex((x) => x.toLowerCase() === h.toLowerCase()); if (i >= 0) { user.splice(i, 1); console.log(`@${h} removed`); } else console.log(`@${h} is not in ${USER_FILE} (seed handles live in references/designers.txt)`); }
  } else die(`unknown handles command: ${sub}`);
  fs.mkdirSync(path.dirname(USER_FILE), { recursive: true });
  fs.writeFileSync(USER_FILE, user.join('\n') + '\n');
}

async function cmdDoctor() {
  const major = parseInt(process.versions.node, 10);
  console.log(`node ${process.versions.node} ${major >= 18 ? 'ok' : 'TOO OLD (need 18+)'}`);
  console.log(`ffmpeg ${hasBin('ffmpeg') ? 'ok' : 'MISSING (no tiles, colors, video frames)'}`);
  console.log(`ffprobe ${hasBin('ffprobe') ? 'ok' : 'missing (only needed when a video has no duration)'}`);
  const handles = loadHandles();
  console.log(`watchlist ${handles.length} handles (${USER_FILE}${fs.existsSync(USER_FILE) ? '' : ', not created yet'} + references/designers.txt)`);
  const t = handles[0] ? await timeline(handles[0], 5) : { error: 'no handle to test with' };
  console.log(`api ${API} ${t.error ? 'FAIL: ' + t.error : `ok (@${handles[0]}: ${t.posts.length} posts)`}`);
  console.log(`project root ${projectRoot() || 'none here (pass --out)'}`);
  if (major < 18 || t.error) process.exit(1);
}

async function main() {
  const argv = process.argv.slice(2);
  const cmd = argv.shift();
  const bool = new Set(['json', 'all', 'no-frames']);
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a.startsWith('--')) { const k = a.slice(2); if (bool.has(k)) flags[k] = true; else { flags[k] = argv[i + 1]; i++; } } else pos.push(a);
  }
  jsonOut = !!flags.json;
  const cmds = { find: () => cmdFind(false), fetch: () => cmdFind(true), latest: cmdLatest, download: cmdDownload, handles: cmdHandles, doctor: cmdDoctor };
  if (!cmds[cmd]) die('usage: xdesign.mjs find|fetch "<idea>" | latest <handle>... | download <url|id>... | handles [list|add|rm|check] | doctor', 2);
  await cmds[cmd]();
}

if (process.argv[1] && fs.realpathSync(process.argv[1]) === fileURLToPath(import.meta.url)) main().catch((e) => die(e.stack || e.message));
