// lib.mjs — pure logic of xdesign.mjs: reading post links and handles, one shape for a post,
// ranking posts against an idea, dominant colors. No network, no files. Tested in
// tests/xdesign.test.mjs.

// Words that say nothing about the subject of a design post.
const STOP = new Set(['ui', 'ux', 'design', 'designs', 'the', 'a', 'an', 'and', 'or', 'for', 'of', 'to', 'in', 'on', 'with', 'my', 'our', 'new', 'like', 'app', 'apps', 'concept', 'screen', 'screens', 'page']);
// Screen types. An idea that names one of these also matches posts that use a sibling word,
// so a "dashboard" idea still finds an "admin panel" of another business type.
const SCREEN_TYPES = {
  dashboard: ['dashboard', 'admin', 'analytics', 'panel', 'saas', 'crm', 'erp', 'console', 'back office', 'backoffice'],
  mobile: ['mobile', 'ios', 'android'],
  landing: ['landing', 'website', 'homepage', 'hero', 'web design'],
};

// ── pure helpers (exported for tests) ───────────────────────────────────
export const slugify = (s) => String(s).toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 60) || 'posts';

export function parsePostRef(ref) {
  const s = String(ref).trim();
  if (/^\d{5,25}$/.test(s)) return { id: s, handle: null };
  const m = s.match(/(?:x|twitter|fxtwitter|vxtwitter|fixupx)\.com\/([A-Za-z0-9_]{1,15})\/status(?:es)?\/(\d{5,25})/i);
  return m ? { id: m[2], handle: m[1] } : null;
}

export function cleanHandle(h) {
  const s = String(h).trim().replace(/^@/, '').replace(/^https?:\/\/(?:www\.)?(?:x|twitter)\.com\//i, '').replace(/[/?#].*$/, '');
  return /^[A-Za-z0-9_]{1,15}$/.test(s) ? s : null;
}

export function parseHandleList(text) {
  const out = [];
  for (const line of String(text).split('\n')) {
    const h = cleanHandle(line.replace(/#.*$/, '').trim().split(/\s+/)[0] || '');
    if (h && !out.some((x) => x.toLowerCase() === h.toLowerCase())) out.push(h);
  }
  return out;
}

function pickVideoUrl(m) {
  const list = (m.variants || m.formats || []).filter((v) => /mp4/i.test(v.content_type || v.container || v.url || '') && v.url);
  if (!list.length) return m.url || null;
  return list.sort((a, b) => (b.bitrate || 0) - (a.bitrate || 0))[0].url;
}

// One shape for a post, from either an FxTwitter status object or the X syndication one.
export function normalizePost(t) {
  if (!t) return null;
  if (t.mediaDetails || t.id_str) { // syndication (fallback for a single post)
    const media = (t.mediaDetails || []).map((m) => m.type === 'photo'
      ? { type: 'photo', url: m.media_url_https + '?name=orig', width: m.original_info?.width, height: m.original_info?.height }
      : { type: 'video', url: pickVideoUrl({ variants: m.video_info?.variants }), width: m.original_info?.width, height: m.original_info?.height, duration: (m.video_info?.duration_millis || 0) / 1000 || undefined });
    return {
      id: t.id_str, handle: t.user?.screen_name, author: t.user?.name, url: `https://x.com/${t.user?.screen_name}/status/${t.id_str}`,
      text: String(t.text || '').replace(/&amp;/g, '&').replace(/\s*https:\/\/t\.co\/\S+/g, '').trim(),
      created_at: t.created_at ? new Date(t.created_at).toISOString() : null, likes: t.favorite_count ?? null, views: null, bookmarks: null,
      media: media.filter((m) => m.url),
    };
  }
  const media = (t.media?.all || []).map((m) => m.type === 'photo'
    ? { type: 'photo', url: m.url, width: m.width, height: m.height }
    : { type: 'video', url: pickVideoUrl(m), width: m.width, height: m.height, duration: m.duration });
  return {
    id: String(t.id), handle: t.author?.screen_name, author: t.author?.name, url: t.url,
    text: String(t.text || '').trim(),
    created_at: t.created_timestamp ? new Date(t.created_timestamp * 1000).toISOString() : null,
    likes: t.likes ?? null, views: t.views ?? null, bookmarks: t.bookmarks ?? null,
    media: media.filter((m) => m.url),
  };
}

export function ideaTerms(idea) {
  const words = String(idea).toLowerCase().split(/[^a-z0-9]+/).filter((w) => w.length > 1);
  const types = Object.keys(SCREEN_TYPES).filter((k) => SCREEN_TYPES[k].some((w) => words.includes(w)) || words.includes(k));
  const typeWords = new Set(types.flatMap((k) => SCREEN_TYPES[k]));
  const subject = [...new Set(words.filter((w) => !STOP.has(w) && !typeWords.has(w)))];
  return { subject, types };
}

const hasWord = (text, w) => {
  const stem = w.length > 4 ? w.replace(/(?:ies|es|s|ing)$/, '') : w;
  return new RegExp(`(^|[^a-z0-9])${stem.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}`, 'i').test(text);
};

// subject word = 3 points each, same screen type = 2. Recency and reach only order posts
// that already match; they never make an unrelated post match (see `matched`).
export function scorePost(post, terms, now = Date.now()) {
  const text = post.text || '';
  const subjectHits = terms.subject.filter((w) => hasWord(text, w));
  const typeHits = terms.types.filter((k) => SCREEN_TYPES[k].some((w) => hasWord(text, w)));
  const matched = subjectHits.length * 3 + typeHits.length * 2;
  const ageDays = post.created_at ? (now - Date.parse(post.created_at)) / 864e5 : 365;
  const recency = Math.max(0, 1 - ageDays / 60);
  const reach = Math.min(1, Math.log10((post.views || post.likes || 0) + 1) / 6);
  return { matched, score: +(matched + recency + reach).toFixed(2), subjectHits, typeHits, ageDays: Math.round(ageDays) };
}

export function rankPosts(posts, idea, { all = false, days = 0, now = Date.now() } = {}) {
  const terms = ideaTerms(idea);
  return posts
    .map((p) => ({ ...p, rank: scorePost(p, terms, now) }))
    .filter((p) => p.media.length && (all || p.rank.matched > 0) && (!days || p.rank.ageDays <= days))
    .sort((a, b) => b.rank.score - a.rank.score || Date.parse(b.created_at) - Date.parse(a.created_at));
}

// Dominant colors of raw RGB24 pixels: 5 bits per channel buckets, averaged, near twins merged.
export function quantize(rgb, max = 8) {
  const buckets = new Map();
  const n = Math.floor(rgb.length / 3);
  for (let i = 0; i < n; i++) {
    const r = rgb[i * 3], g = rgb[i * 3 + 1], b = rgb[i * 3 + 2];
    const k = (r >> 3) << 10 | (g >> 3) << 5 | (b >> 3);
    const e = buckets.get(k) || [0, 0, 0, 0];
    e[0] += r; e[1] += g; e[2] += b; e[3]++; buckets.set(k, e);
  }
  const cols = [...buckets.values()].map(([r, g, b, c]) => ({ r: r / c, g: g / c, b: b / c, c })).sort((a, b) => b.c - a.c);
  const kept = [];
  for (const col of cols) {
    const twin = kept.find((k) => Math.abs(k.r - col.r) + Math.abs(k.g - col.g) + Math.abs(k.b - col.b) < 36);
    if (twin) twin.c += col.c; else kept.push({ ...col });
  }
  const hex = (v) => Math.round(v).toString(16).padStart(2, '0');
  return kept.sort((a, b) => b.c - a.c).slice(0, max)
    .map((k) => ({ hex: `#${hex(k.r)}${hex(k.g)}${hex(k.b)}`, share: +((k.c / n) * 100).toFixed(1) }));
}
