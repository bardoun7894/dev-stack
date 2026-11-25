// media.mjs — what ffmpeg does for xdesign.mjs: sampled colors, tiles of large images, video
// frames, contact sheets. Plus the two pages written for people: the candidates gallery and
// the folder README. Every ffmpeg step is optional: without ffmpeg the files are still saved.

import fs from 'node:fs';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { quantize } from './lib.mjs';

export const hasBin = (b) => spawnSync(b, ['-version'], { stdio: 'ignore' }).status === 0;
const ff = (args, opts = {}) => spawnSync('ffmpeg', ['-v', 'error', '-y', ...args], opts);

export function palette(file) {
  const r = ff(['-i', file, '-frames:v', '1', '-vf', 'scale=200:150:flags=neighbor', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], { maxBuffer: 1 << 24 });
  return r.status === 0 && r.stdout?.length ? quantize(r.stdout) : [];
}

// 2 x 2 tiles with a small overlap, so text on a seam is whole in at least one tile.
export function tiles(file, base) {
  const out = [];
  [['0', '0'], ['iw*0.46', '0'], ['0', 'ih*0.46'], ['iw*0.46', 'ih*0.46']].forEach(([x, y], i) => {
    const f = `${base}-t${i + 1}.jpg`;
    if (ff(['-i', file, '-vf', `crop=iw*0.54:ih*0.54:${x}:${y}`, '-q:v', '2', f]).status === 0) out.push(path.basename(f));
  });
  return out;
}

export function videoFrames(file, base, duration) {
  let dur = duration;
  if (!dur) {
    const p = spawnSync('ffprobe', ['-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', file], { encoding: 'utf8' });
    dur = parseFloat(p.stdout) || 0;
  }
  if (!dur) return { frames: [], sheet: null, duration: null };
  const n = Math.max(6, Math.min(16, Math.round(dur / 1.5)));
  const fps = (n / dur).toFixed(4);
  ff(['-i', file, '-vf', `fps=${fps},scale='min(1600,iw)':-2`, '-frames:v', String(n), '-q:v', '3', `${base}-f%02d.jpg`]);
  const sheet = `${base}-sheet.jpg`;
  const s = ff(['-i', file, '-vf', `fps=${fps},scale=480:-2,tile=4x${Math.ceil(n / 4)}`, '-frames:v', '1', '-q:v', '3', sheet]);
  const stem = path.basename(base) + '-f';
  const frames = fs.readdirSync(path.dirname(base)).filter((f) => f.startsWith(stem) && f.endsWith('.jpg')).sort();
  return { frames, sheet: s.status === 0 ? path.basename(sheet) : null, duration: +dur.toFixed(1) };
}

// One image of all candidate thumbnails, 4 per row, in candidate order (1 is top left).
// Lets an agent that can see images judge the whole list in one look.
export function contactSheet(files, out) {
  if (!files.length) return false;
  const cell = 'scale=480:360:force_original_aspect_ratio=decrease,pad=480:360:(ow-iw)/2:(oh-ih)/2:color=white,setsar=1';
  const args = files.flatMap((f) => ['-i', f]);
  const chains = files.map((_, i) => `[${i}:v]${cell}[c${i}]`).join(';');
  const cols = Math.min(4, files.length), rows = Math.ceil(files.length / cols);
  const layout = files.map((_, i) => `${(i % cols) * 480}_${Math.floor(i / cols) * 360}`).join('|');
  const stack = files.length === 1 ? `[c0]copy[o]` : `${files.map((_, i) => `[c${i}]`).join('')}xstack=inputs=${files.length}:layout=${layout}:fill=white[o]`;
  const r = ff([...args, '-filter_complex', `${chains};${stack}`, '-map', '[o]', '-frames:v', '1', '-q:v', '3', out]);
  return r.status === 0 && rows > 0;
}

const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const num = (n) => (n == null ? '?' : n >= 1000 ? (n / 1000).toFixed(1) + 'k' : String(n));

// The page the user picks from. Thumbnails are local files (thumbs/NN.jpg) when they were
// saved, else the remote small image. No script, no external assets.
export function galleryHtml(idea, candidates) {
  const cards = candidates.map((c) => {
    const m = c.media[0];
    const why = [...(c.rank?.subjectHits || []), ...(c.rank?.typeHits || []).map((t) => 'type: ' + t)].join(', ') || 'listed without a word match';
    return `<article><a href="${esc(c.url)}" target="_blank" rel="noopener"><img loading="lazy" src="${esc(c.thumbFile || m.thumb || m.url)}" alt="candidate ${c.n}"></a>
<div class="b"><p class="n">${c.n}${m.type !== 'photo' ? ' <span>video ' + Math.round(m.duration || 0) + ' s</span>' : ''}${c.media.length > 1 ? ' <span>' + c.media.length + ' images</span>' : ''}</p>
<p class="t">${esc((c.text || '').slice(0, 140))}</p>
<p class="m">@${esc(c.handle)} · ${esc((c.created_at || '').slice(0, 10))} · ${num(c.likes)} likes · ${num(c.bookmarks)} saves · ${num(c.views)} views</p>
<p class="m">match: ${esc(why)} · score ${c.rank?.score ?? ''}</p></div></article>`;
  }).join('\n');
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>X design candidates</title><style>
:root{--bg:#f6f6f4;--card:#fff;--ink:#16181c;--mute:#6b7078;--line:#e3e3df}
@media(prefers-color-scheme:dark){:root{--bg:#121315;--card:#1c1e21;--ink:#f1f1ee;--mute:#9aa0a8;--line:#2c2f33}}
*{box-sizing:border-box}body{margin:0;padding:24px 16px 48px;background:var(--bg);color:var(--ink);font:15px/1.45 system-ui,sans-serif}
h1{font-size:22px;margin:0 0 4px}header p{margin:0 0 20px;color:var(--mute)}
main{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:16px}
article{background:var(--card);border:1px solid var(--line);border-radius:14px;overflow:hidden}
img{display:block;width:100%;aspect-ratio:4/3;object-fit:cover;background:var(--line)}
.b{padding:12px 14px 14px}p{margin:0}.n{font-size:26px;font-weight:700;line-height:1}.n span{font-size:12px;font-weight:500;color:var(--mute);margin-left:8px}
.t{margin:8px 0 6px}.m{font-size:12.5px;color:var(--mute)}
</style></head><body><header><h1>${esc(idea)}</h1><p>${candidates.length} candidate posts from X, best first. Tell the agent the numbers you want, for example "take 2 and 5".</p></header>
<main>
${cards}
</main></body></html>
`;
}

export function readme(manifest) {
  const rows = manifest.posts.map((p) => {
    const files = p.media.filter((m) => !m.error).map((m) => `\`${m.file}\`${m.tiles?.length ? ` (+${m.tiles.length} tiles)` : ''}${m.frames?.length ? ` (+${m.frames.length} frames, \`${m.sheet}\`)` : ''}`).join('<br>');
    const colors = (p.media.find((m) => m.palette?.length)?.palette || []).slice(0, 6).map((c) => `\`${c.hex}\` ${c.share}%`).join(' ');
    return `| ${p.n} | [${(p.text || '').replace(/[|\n]/g, ' ').slice(0, 70) || p.id}](${p.url}) | @${p.handle} | ${(p.created_at || '').slice(0, 10)} | ${p.likes ?? ''} / ${p.views ?? ''} | ${files} | ${colors} |`;
  });
  return `# X design references — ${manifest.subjects.join(' · ')}\n\nThird-party work, saved for reference only. Do not ship these files or copy a post one-to-one.\nSource of truth for authors, links and colors is \`manifest.json\`.\n\n| # | Post | Author | Date | Likes / views | Files | Main colors (share of pixels) |\n|---|---|---|---|---|---|---|\n${rows.join('\n')}\n`;
}
