// save.mjs — save chosen posts into a reference folder: images at original size (tiles when a
// side is long, sampled colors), videos with frames and a contact sheet, manifest.json and
// README.md. A post is recorded only when at least one of its files was saved; a post whose
// files all failed is left out, so the next run tries it again instead of skipping it.

import fs from 'node:fs';
import path from 'node:path';
import { saveUrl } from './net.mjs';
import { hasBin, palette, tiles, videoFrames, readme } from './media.mjs';

const MAX_DOWNLOADS = 30, MAX_VIDEO_MB = 80, MAX_VIDEO_SEC = 240;
const TILE_MIN_SIDE = 2600; // a side this long, and small labels are lost when the whole image is viewed at once

const ok = (entry) => entry.media.some((m) => !m.error);

async function saveMedia(post, stem, dir, { ff, noFrames, log }) {
  const media = [];
  for (let k = 0; k < post.media.length; k++) {
    const m = post.media[k];
    const base = path.join(dir, post.media.length > 1 ? `${stem}-${k + 1}` : stem);
    try {
      if (m.type === 'photo') {
        const file = `${base}.${(m.url.match(/\.(jpg|jpeg|png|webp)/i)?.[1] || 'jpg').toLowerCase()}`;
        const item = { type: 'photo', file: path.basename(file), width: m.width, height: m.height, bytes: await saveUrl(m.url, file), source: m.url };
        if (ff) {
          item.palette = palette(file);
          if (Math.max(m.width || 0, m.height || 0) >= TILE_MIN_SIDE) item.tiles = tiles(file, base);
        }
        media.push(item);
      } else {
        if ((m.duration || 0) > MAX_VIDEO_SEC) throw new Error(`video is ${Math.round(m.duration)} s, over the ${MAX_VIDEO_SEC} s cap`);
        const file = `${base}.mp4`;
        const item = { type: 'video', file: path.basename(file), width: m.width, height: m.height, bytes: await saveUrl(m.url, file, MAX_VIDEO_MB), source: m.url };
        if (ff && !noFrames) {
          Object.assign(item, videoFrames(file, base, m.duration));
          if (item.frames?.length) item.palette = palette(path.join(dir, item.frames[Math.floor(item.frames.length / 2)]));
        }
        fs.writeFileSync(path.join(dir, '.gitignore'), '*.mp4\n');
        media.push(item);
      }
    } catch (e) {
      media.push({ type: m.type, error: e.message, source: m.url });
      log(`  ${post.id} media ${k + 1}: ${e.message}`);
    }
  }
  return media;
}

export async function savePosts(posts, subject, dir, { noFrames = false, log = console.error } = {}) {
  fs.mkdirSync(dir, { recursive: true });
  const manifestFile = path.join(dir, 'manifest.json');
  const manifest = fs.existsSync(manifestFile) ? JSON.parse(fs.readFileSync(manifestFile, 'utf8')) : { source: 'x', subjects: [], posts: [] };
  manifest.posts = manifest.posts.filter(ok); // drop entries an older version recorded with no file
  if (!manifest.subjects.includes(subject)) manifest.subjects.push(subject);
  const ff = hasBin('ffmpeg');
  if (!ff) log('ffmpeg not found: no tiles, no colors, no video frames');
  let n = manifest.posts.reduce((m, p) => Math.max(m, p.n), 0), added = 0, failed = 0;

  for (const post of posts.slice(0, MAX_DOWNLOADS)) {
    if (manifest.posts.some((p) => p.id === post.id)) { log(`skip ${post.id} (already saved)`); continue; }
    const stem = `${String(n + 1).padStart(2, '0')}-${post.handle}-${post.id}`;
    const entry = { n: n + 1, id: post.id, url: post.url, handle: post.handle, author: post.author, text: post.text, created_at: post.created_at, likes: post.likes, views: post.views, bookmarks: post.bookmarks, rank: post.rank || null, media: await saveMedia(post, stem, dir, { ff, noFrames, log }) };
    if (!ok(entry)) { failed++; log(`FAILED ${post.url}: no file could be downloaded; not recorded, run the same command again`); continue; }
    n++; manifest.posts.push(entry); added++;
    log(`saved ${stem}  ${entry.media.map((x) => x.error ? 'ERR' : x.type === 'photo' ? `${x.width}x${x.height}${x.tiles ? ' +' + x.tiles.length + ' tiles' : ''}` : `video ${x.duration ?? '?'}s ${x.frames?.length ?? 0} frames`).join(', ')}`);
  }
  manifest.generated = new Date().toISOString();
  fs.writeFileSync(manifestFile, JSON.stringify(manifest, null, 2) + '\n');
  fs.writeFileSync(path.join(dir, 'README.md'), readme(manifest));
  console.log(`${added} new post(s) saved${failed ? `, ${failed} failed (run again)` : ''}, ${manifest.posts.length} in folder\n${dir}`);
  return { added, failed, dir };
}
