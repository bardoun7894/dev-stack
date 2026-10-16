// post.json loading, validation and pure helpers. No I/O beyond reading post.json and the file check.
import fs from 'node:fs';
import path from 'node:path';

export const PLATFORM_ORDER = ['youtube', 'tiktok', 'facebook_page', 'facebook_profile', 'linkedin', 'drive', 'portfolio'];
const SLUG_RE = /^[a-z0-9-]+$/;
const YT_TITLE_MAX = 100;
const TIKTOK_CAPTION_MAX = 2200;

export function normalizeText(s) {
  return String(s).normalize('NFC').replace(/\s+/g, ' ').trim();
}

export function validatePost(post, { now = new Date(), fileExists = fs.existsSync } = {}) {
  const errors = [];
  if (!post || typeof post !== 'object' || Array.isArray(post)) return ['post.json must be an object'];

  if (typeof post.slug !== 'string' || !SLUG_RE.test(post.slug)) {
    errors.push(`slug must match [a-z0-9-]+ (got ${JSON.stringify(post.slug)})`);
  }

  if (typeof post.video !== 'string' || !post.video) {
    errors.push('video must be a path');
  } else {
    if (!/\.mp4$/i.test(post.video)) errors.push(`video must be an .mp4 file (got ${post.video})`);
    if (!fileExists(post.video)) errors.push(`video file not found: ${post.video}`);
  }

  if (post.schedule !== null && post.schedule !== undefined) {
    const t = typeof post.schedule === 'string' && /Z$/.test(post.schedule) ? Date.parse(post.schedule) : NaN;
    if (Number.isNaN(t)) errors.push(`schedule must be ISO UTC ending in Z or null (got ${JSON.stringify(post.schedule)})`);
    else if (t <= now.getTime()) errors.push(`schedule must be in the future (got ${post.schedule})`);
  }

  const platforms = post.platforms;
  if (!platforms || typeof platforms !== 'object' || Object.keys(platforms).length === 0) {
    errors.push('no platforms in post.json');
    return errors;
  }
  for (const name of Object.keys(platforms)) {
    if (!PLATFORM_ORDER.includes(name)) errors.push(`unknown platform ${name}`);
  }

  const yt = platforms.youtube;
  if (yt) {
    if (typeof yt.title !== 'string' || !yt.title) errors.push('youtube.title is required');
    else if (yt.title.length > YT_TITLE_MAX) errors.push(`youtube.title must be <= ${YT_TITLE_MAX} chars (got ${yt.title.length})`);
    if (yt.tags !== undefined && !Array.isArray(yt.tags)) errors.push('youtube.tags must be an array');
  }
  const tt = platforms.tiktok;
  if (tt) {
    if (typeof tt.caption !== 'string' || !tt.caption) errors.push('tiktok.caption is required');
    else if (tt.caption.length > TIKTOK_CAPTION_MAX) errors.push(`tiktok.caption must be <= ${TIKTOK_CAPTION_MAX} chars (got ${tt.caption.length})`);
  }
  if (platforms.linkedin && (typeof platforms.linkedin.text !== 'string' || !platforms.linkedin.text)) {
    errors.push('linkedin.text is required');
  }
  if (platforms.portfolio && (typeof platforms.portfolio.title !== 'string' || !platforms.portfolio.title)) {
    errors.push('portfolio.title is required');
  }
  return errors;
}

export function loadPost(postPath, opts = {}) {
  const abs = path.resolve(postPath);
  let raw;
  try {
    raw = JSON.parse(fs.readFileSync(abs, 'utf8'));
  } catch (e) {
    throw new Error(`cannot read ${abs}: ${e.message}`);
  }
  const dir = path.dirname(abs);
  if (raw && typeof raw.video === 'string' && !path.isAbsolute(raw.video)) {
    raw.video = path.join(dir, raw.video);
  }
  const errors = validatePost(raw, opts);
  if (errors.length) throw new Error(`invalid post.json:\n  - ${errors.join('\n  - ')}`);
  return { ...raw, dir, file: abs };
}

export function selectPlatforms(post, only) {
  const present = PLATFORM_ORDER.filter((p) => post.platforms && post.platforms[p] !== undefined);
  if (!only || only.length === 0) return present;
  for (const name of only) {
    if (!PLATFORM_ORDER.includes(name)) throw new Error(`unknown platform: ${name}`);
    if (!present.includes(name)) throw new Error(`not in post.json: ${name}`);
  }
  return PLATFORM_ORDER.filter((p) => only.includes(p));
}

export function scheduleParts(iso) {
  const d = new Date(iso);
  const pad = (n) => String(n).padStart(2, '0');
  const h = d.getUTCHours();
  const h12 = h % 12 === 0 ? 12 : h % 12;
  return {
    date: d.toISOString().slice(0, 10),
    time24: `${pad(h)}:${pad(d.getUTCMinutes())}`,
    time12: `${h12}:${pad(d.getUTCMinutes())} ${h < 12 ? 'AM' : 'PM'}`,
    iso: d.toISOString(),
  };
}

// Platforms still to run: anything whose recorded result is not ok. Never re-post an ok platform.
export function pendingPlatforms(results, names) {
  return names.filter((n) => !(results && results[n] && results[n].ok === true));
}
