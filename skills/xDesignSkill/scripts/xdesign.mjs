#!/usr/bin/env node
// xdesign.mjs — pull UI/UX design references from the latest X (Twitter) posts, any account.
//
//   xdesign find     "<idea>" [--links url,url] [--handles a,b] [--no-web] [--no-watchlist] [--no-pool]
//                             [--days N] [--min-likes N] [--sort score|likes|recent]
//                             [--per-author N] [--limit N] [--all] [--out DIR] [--json]
//   xdesign pick     <n>... [--from DIR] [--no-frames]      download the chosen candidates
//   xdesign fetch    "<idea>" [find flags] [--top N]         find, then pick the top N
//   xdesign download <post-url|id>... [--out DIR] [--subject "<text>"] [--no-frames]
//   xdesign latest   <handle>... [--limit N] [--json]
//   xdesign handles  [list | add <handle>... | rm <handle>... | check [<handle>...]]
//   xdesign doctor
//
// `find` gathers posts four ways, none needing an X login: web search for post links about
// the idea (any account), the newest posts of the authors that search turned up, the newest
// posts of a watchlist, and the pool of posts earlier runs saw. It ranks them by closeness to the idea and by how well they
// were received, and writes a gallery to choose from. `pick` saves the chosen ones: images
// at original size, cut into tiles when large, real colors sampled; videos cut into frames.
// Reference use only — see SKILL.md. Logic: lib.mjs. Network: net.mjs. ffmpeg + pages: media.mjs.

import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { fileURLToPath } from 'node:url';
import { slugify, parsePostRef, cleanHandle, parseHandleList, ideaTerms, rankPosts } from './lib.mjs';
import { API, sleep, timeline, getPost, webDiscover, saveUrl, loadPool, savePool } from './net.mjs';
import { hasBin, palette, tiles, videoFrames, contactSheet, galleryHtml, readme } from './media.mjs';

export * from './lib.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SEED_FILE = path.join(HERE, '..', 'references', 'designers.txt');
const USER_FILE = process.env.XDESIGN_HANDLES || path.join(os.homedir(), '.config', 'xdesign', 'handles.txt');
const MAX_HANDLES = 30, MAX_DOWNLOADS = 30, MAX_HYDRATE = 30, MAX_NEW_AUTHORS = 6, HANDLE_DELAY_MS = 900;
const MAX_VIDEO_MB = 80, MAX_VIDEO_SEC = 240;
const TILE_MIN_WIDTH = 2600; // wider than this, small labels are lost when the whole image is viewed at once

const flags = {}; const pos = [];
let jsonOut = false;
function die(msg, code = 1) { console.error('xdesign: ' + msg); process.exit(code); }
const log = (...a) => { if (!jsonOut) console.error(...a); };
const int = (v, dflt) => parseInt(v ?? dflt, 10) || dflt;
const readJson = (f) => JSON.parse(fs.readFileSync(f, 'utf8'));

function loadHandles() {
  const read = (f) => (fs.existsSync(f) ? parseHandleList(fs.readFileSync(f, 'utf8')) : []);
  const all = [...read(USER_FILE), ...read(SEED_FILE)];
  return all.filter((h, i) => all.findIndex((x) => x.toLowerCase() === h.toLowerCase()) === i);
}

function projectRoot() {
  let dir = process.cwd();
  while (dir !== path.dirname(dir)) {
    if (dir !== os.homedir() && (fs.existsSync(path.join(dir, '.git')) || fs.existsSync(path.join(dir, '.claude')))) return dir;
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

// ── saving chosen posts ─────────────────────────────────────────────────
async function savePosts(posts, subject, dir = outDir(subject)) {
  fs.mkdirSync(dir, { recursive: true });
  const manifestFile = path.join(dir, 'manifest.json');
  const manifest = fs.existsSync(manifestFile) ? readJson(manifestFile) : { source: 'x', subjects: [], posts: [] };
  if (!manifest.subjects.includes(subject)) manifest.subjects.push(subject);
  const ff = hasBin('ffmpeg');
  if (!ff) log('ffmpeg not found: no tiles, no colors, no video frames');
  let n = manifest.posts.reduce((m, p) => Math.max(m, p.n), 0), added = 0;

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
          const file = `${base}.${(m.url.match(/\.(jpg|jpeg|png|webp)/i)?.[1] || 'jpg').toLowerCase()}`;
          const item = { type: 'photo', file: path.basename(file), width: m.width, height: m.height, bytes: await saveUrl(m.url, file), source: m.url };
          if (ff) {
            item.palette = palette(file);
            if ((m.width || 0) >= TILE_MIN_WIDTH) item.tiles = tiles(file, base);
          }
          entry.media.push(item);
        } else {
          if ((m.duration || 0) > MAX_VIDEO_SEC) throw new Error(`video is ${Math.round(m.duration)} s, over the ${MAX_VIDEO_SEC} s cap`);
          const file = `${base}.mp4`;
          const item = { type: 'video', file: path.basename(file), width: m.width, height: m.height, bytes: await saveUrl(m.url, file, MAX_VIDEO_MB), source: m.url };
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
  console.log(`${added} new post(s) saved, ${manifest.posts.length} in folder\n${dir}`);
}

function printPosts(posts) {
  if (jsonOut) { console.log(JSON.stringify(posts, null, 2)); return; }
  if (!posts.length) { console.log('no posts'); return; }
  for (const p of posts) {
    const media = p.media.map((m) => m.type === 'photo' ? `photo ${m.width}x${m.height}` : `video ${Math.round(m.duration || 0)}s`).join(', ');
    const why = p.rank ? ` · score ${p.rank.score} [${[...p.rank.subjectHits, ...p.rank.typeHits.map((t) => 'type:' + t)].join(' ') || 'no word match'}]` : '';
    console.log(`${p.n ? String(p.n).padStart(2) + '. ' : ''}${(p.created_at || '').slice(0, 10)}  @${p.handle}  ${p.text.replace(/\s+/g, ' ').slice(0, 80)}\n      ${p.url}\n      ${media} · likes ${p.likes ?? '?'} · saves ${p.bookmarks ?? '?'} · views ${p.views ?? '?'}${why}`);
  }
}

// ── gathering candidates ────────────────────────────────────────────────
async function readTimelines(handles, label) {
  const posts = [];
  for (const h of handles) {
    const t = await timeline(h);
    log(`${label} @${h}: ${t.error || t.posts.length + ' media posts'}`);
    posts.push(...t.posts);
    await sleep(HANDLE_DELAY_MS);
  }
  return posts;
}

async function hydrate(refs) {
  const posts = [];
  for (const r of refs.slice(0, MAX_HYDRATE)) {
    const p = await getPost(r.id, r.handle);
    if (p?.media.length) posts.push(p);
    await sleep(300);
  }
  return posts;
}

async function gather(idea) {
  const posts = [];
  const watch = flags['no-watchlist'] ? [] : (flags.handles ? String(flags.handles).split(',').map(cleanHandle).filter(Boolean) : loadHandles()).slice(0, MAX_HANDLES);
  const known = new Set(watch.map((h) => h.toLowerCase()));
  const found = await hydrate(String(flags.links || '').split(',').map(parsePostRef).filter(Boolean));
  if (found.length) log(`link ${found.length} passed post(s) with an image or video`);

  if (!flags['no-web']) {
    const web = await webDiscover(idea);
    web.notes.forEach((n) => log('web  ' + n));
    const got = await hydrate(web.refs);
    log(`web  ${web.refs.length} post links, ${got.length} with an image or video`);
    found.push(...got);
    if (web.blocked) log(`web  search is blocked for now. For fresh posts, run these in your own web search tool and pass the x.com post links with --links:\n       ${web.queries.join('\n       ')}`);
  }
  // The authors of the best matching finds usually post more of the same: read them too.
  const authors = [...new Set(rankPosts(found, idea).map((p) => p.handle))].filter((h) => h && !known.has(h.toLowerCase())).slice(0, MAX_NEW_AUTHORS);
  posts.push(...found, ...await readTimelines(authors, 'new '));
  posts.push(...await readTimelines(watch, 'list'));
  if (flags['no-pool']) return posts;
  const pool = loadPool(); // fresh posts first: rankPosts keeps the first copy of an id
  log(`pool ${pool.length} posts from earlier runs, ${savePool(posts)} after this one`);
  return [...posts, ...pool];
}

async function cmdFind(thenPick) {
  const idea = pos.join(' ').trim();
  if (!idea) die('give the idea, e.g. find "transport fleet dashboard"');
  const terms = ideaTerms(idea);
  log(`idea words: ${terms.subject.join(', ') || '(none)'} · screen type: ${terms.types.join(', ') || '(none)'}`);
  const ranked = rankPosts(await gather(idea), idea, { all: !!flags.all, days: int(flags.days, 0), minLikes: int(flags['min-likes'], 0), sort: String(flags.sort || 'score'), perAuthor: flags['per-author'] === undefined ? 3 : int(flags['per-author'], 0) })
    .slice(0, Math.min(24, int(flags.limit, 12))).map((p, i) => ({ ...p, n: i + 1 }));
  if (!ranked.length) die('no post matches the idea; add sibling words, pass --links, or use --all', 3);

  const dir = outDir(idea);
  fs.mkdirSync(path.join(dir, 'thumbs'), { recursive: true });
  const thumbs = [];
  for (const c of ranked) {
    const file = path.join('thumbs', `${String(c.n).padStart(2, '0')}.jpg`);
    try { await saveUrl(c.media[0].thumb || c.media[0].url, path.join(dir, file)); c.thumbFile = file; thumbs.push(path.join(dir, file)); } catch { /* gallery falls back to the remote image */ }
  }
  fs.writeFileSync(path.join(dir, 'candidates.json'), JSON.stringify({ idea, generated: new Date().toISOString(), candidates: ranked }, null, 2) + '\n');
  fs.writeFileSync(path.join(dir, 'gallery.html'), galleryHtml(idea, ranked));
  const sheet = thumbs.length === ranked.length && hasBin('ffmpeg') && contactSheet(thumbs, path.join(dir, 'candidates-sheet.jpg'));
  printPosts(ranked);
  if (!jsonOut) console.log(`\n${ranked.length} candidates\ngallery  ${path.join(dir, 'gallery.html')}${sheet ? `\nsheet    ${path.join(dir, 'candidates-sheet.jpg')}  (4 per row, number 1 is top left)` : ''}\nchoose   xdesign pick <numbers> --from "${dir}"`);
  if (thenPick) await savePosts(ranked.slice(0, Math.min(MAX_DOWNLOADS, int(flags.top, 4))), idea, dir);
}

function latestCandidatesDir() {
  const base = path.join(projectRoot() || '', 'design', 'inspiration');
  if (!fs.existsSync(base)) return null;
  const dirs = fs.readdirSync(base).map((d) => path.join(base, d)).filter((d) => fs.existsSync(path.join(d, 'candidates.json')));
  return dirs.sort((a, b) => fs.statSync(path.join(b, 'candidates.json')).mtimeMs - fs.statSync(path.join(a, 'candidates.json')).mtimeMs)[0] || null;
}

async function cmdPick() {
  const dir = flags.from ? path.resolve(String(flags.from)) : latestCandidatesDir();
  if (!dir || !fs.existsSync(path.join(dir, 'candidates.json'))) die('no candidates.json found; run find first or pass --from DIR');
  const { idea, candidates } = readJson(path.join(dir, 'candidates.json'));
  const wanted = pos.flatMap((a) => a.split(',')).map((a) => parseInt(a, 10)).filter(Boolean);
  const chosen = wanted.map((n) => candidates.find((c) => c.n === n)).filter(Boolean);
  if (!chosen.length) die(`give candidate numbers between 1 and ${candidates.length}`);
  await savePosts(chosen, idea, dir);
  const known = new Set(loadHandles().map((h) => h.toLowerCase()));
  const fresh = [...new Set(chosen.map((c) => c.handle))].filter((h) => !known.has(h.toLowerCase()));
  if (fresh.length) console.log(`not on the watchlist: ${fresh.map((h) => '@' + h).join(' ')}  (keep them: xdesign handles add ${fresh.join(' ')})`);
}

async function cmdLatest() {
  const handles = pos.map(cleanHandle).filter(Boolean);
  if (!handles.length) die('give at least one handle');
  const seen = new Set();
  printPosts((await readTimelines(handles, '')).filter((p) => !seen.has(p.id) && seen.add(p.id))
    .sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at)).slice(0, Math.min(MAX_DOWNLOADS, int(flags.limit, 12))));
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
  await savePosts(posts, String(flags.subject || posts[0].text || posts[0].id));
}

async function cmdHandles() {
  const sub = pos.shift() || 'list';
  const user = fs.existsSync(USER_FILE) ? parseHandleList(fs.readFileSync(USER_FILE, 'utf8')) : [];
  if (sub === 'list') { console.log(loadHandles().join('\n')); return; }
  if (sub === 'check') {
    const uiWords = /\b(ui|ux|dashboard|app|website|landing|interface|figma|saas|design)\b/i;
    for (const h of pos.length ? pos.map(cleanHandle).filter(Boolean) : loadHandles()) {
      const t = await timeline(h);
      const ui = t.posts.filter((p) => uiWords.test(p.text)).length;
      console.log(`${t.error ? 'FAIL' : ui >= 3 ? 'ok  ' : 'weak'}  @${h}  media posts ${t.posts.length}  ui-titled ${ui}  newest ${t.posts[0]?.created_at?.slice(0, 10) || '-'}${t.error ? '  ' + t.error : ''}`);
      await sleep(HANDLE_DELAY_MS);
    }
    return;
  }
  const names = pos.map(cleanHandle).filter(Boolean);
  if (!names.length) die(`handles ${sub}: give at least one handle`);
  if (sub !== 'add' && sub !== 'rm') die(`unknown handles command: ${sub}`);
  for (const h of names) {
    const i = user.findIndex((x) => x.toLowerCase() === h.toLowerCase());
    if (sub === 'rm') {
      if (i >= 0) { user.splice(i, 1); console.log(`@${h} removed`); } else console.log(`@${h} is not in ${USER_FILE} (seed handles live in references/designers.txt)`);
    } else if (i >= 0) console.log(`@${h} already listed`);
    else {
      const t = await timeline(h);
      if (t.error) console.log(`@${h} not added: ${t.error}`);
      else { user.unshift(h); console.log(`@${h} added (${t.posts.length} media posts, newest ${t.posts[0].created_at?.slice(0, 10)})`); }
    }
  }
  fs.mkdirSync(path.dirname(USER_FILE), { recursive: true });
  fs.writeFileSync(USER_FILE, user.join('\n') + '\n');
}

async function cmdDoctor() {
  const major = parseInt(process.versions.node, 10);
  console.log(`node ${process.versions.node} ${major >= 18 ? 'ok' : 'TOO OLD (need 18+)'}`);
  console.log(`ffmpeg ${hasBin('ffmpeg') ? 'ok' : 'MISSING (no tiles, colors, video frames, candidate sheet)'}`);
  const handles = loadHandles();
  console.log(`watchlist ${handles.length} handles (${USER_FILE}${fs.existsSync(USER_FILE) ? '' : ', not created yet'} + references/designers.txt)`);
  const t = handles[0] ? await timeline(handles[0], 5) : { error: 'no handle to test with' };
  console.log(`api ${API} ${t.error ? 'FAIL: ' + t.error : `ok (@${handles[0]}: ${t.posts.length} posts)`}`);
  const web = await webDiscover('dashboard', { max: 5 });
  console.log(`web search ${web.blocked ? 'BLOCKED for now (rate limit; pass --links or wait)' : web.refs.length ? 'ok' : 'FAIL'} (${web.notes.join('; ')})`);
  console.log(`pool ${loadPool().length} saved posts`);
  console.log(`project root ${projectRoot() || 'none here (pass --out)'}`);
  if (major < 18 || t.error) process.exit(1);
}

async function main() {
  const argv = process.argv.slice(2);
  const cmd = argv.shift();
  const bool = new Set(['json', 'all', 'no-frames', 'no-web', 'no-watchlist', 'no-pool']);
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a.startsWith('--')) { const k = a.slice(2); if (bool.has(k)) flags[k] = true; else { flags[k] = argv[i + 1]; i++; } } else pos.push(a);
  }
  jsonOut = !!flags.json;
  const cmds = { find: () => cmdFind(false), fetch: () => cmdFind(true), pick: cmdPick, latest: cmdLatest, download: cmdDownload, handles: cmdHandles, doctor: cmdDoctor };
  if (!cmds[cmd]) die('usage: xdesign find|fetch "<idea>" | pick <n>... | download <url|id>... | latest <handle>... | handles [list|add|rm|check] | doctor', 2);
  await cmds[cmd]();
}

if (process.argv[1] && fs.realpathSync(process.argv[1]) === fileURLToPath(import.meta.url)) main().catch((e) => die(e.stack || e.message));
