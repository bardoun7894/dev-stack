// net.mjs — every network call of xdesign.mjs: the public FxTwitter API (timelines, single
// posts), the X syndication fallback, web search for post links, file downloads; and the
// local cache that makes runs repeatable. No key and no X login anywhere.

import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { normalizePost, extractPostRefs, searchQueries, slugify } from './lib.mjs';

export const API = process.env.XDESIGN_API || 'https://api.fxtwitter.com';
const SEARX = process.env.SEARXNG_URL || 'http://100.64.0.1:8888';
const UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36';
export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function get(url, { json = true, timeout = 25000 } = {}) {
  let res;
  try { res = await fetch(url, { headers: { 'user-agent': UA, accept: json ? 'application/json' : 'text/html', 'accept-language': 'en-US,en;q=0.9' }, signal: AbortSignal.timeout(timeout) }); }
  catch (e) { return { ok: false, status: 0, error: e.message }; }
  let body = null;
  try { body = json ? await res.json() : await res.text(); } catch { /* unreadable body */ }
  return { ok: res.ok, status: res.status, body };
}

// The API answers 404 or an empty list at random when its upstream throttles, and the two
// timeline endpoints fail independently. So: media, then statuses, then media again, with
// a growing wait. Only three misses in a row count as "no data".
// Reposts are kept (they are other designers' posts); replies are dropped.
export async function timeline(handle, count = 40) {
  const tries = [['media', 0], ['statuses', 1200], ['media', 3000]];
  let last = '';
  for (const [ep, wait] of tries) {
    if (wait) await sleep(wait);
    const r = await get(`${API}/2/profile/${encodeURIComponent(handle)}/${ep}?count=${count}`);
    const posts = (r.body?.results || []).filter((t) => !t.replying_to).map(normalizePost).filter((p) => p && p.media.length);
    if (r.ok && posts.length) return { handle, posts };
    last = r.ok ? 'empty answer' : `http ${r.status}${r.error ? ' ' + r.error : ''}`;
  }
  return { handle, error: `no data after 3 tries (${last}); the account may not exist, or the API is throttling: retry later`, posts: [] };
}

export async function getPost(id, handle) {
  for (const wait of [0, 1500]) {
    if (wait) await sleep(wait);
    const r = await get(`${API}/${handle || 'i'}/status/${id}`);
    if (r.ok && r.body?.tweet) return normalizePost(r.body.tweet);
  }
  const token = ((Number(id) / 1e15) * Math.PI).toString(36).replace(/(0+|\.)/g, '');
  const s = await get(`https://cdn.syndication.twimg.com/tweet-result?id=${id}&token=${token}`);
  return s.ok && s.body?.id_str ? normalizePost(s.body) : null;
}

// ── local cache: search pages for a day, and a pool of every post seen ──
const CACHE = process.env.XDESIGN_CACHE || path.join(os.homedir(), '.cache', 'xdesign');
const POOL = path.join(CACHE, 'pool.json'), POOL_MAX = 2000, SEARCH_TTL_MS = 24 * 3600e3;
const readJson = (f) => { try { return JSON.parse(fs.readFileSync(f, 'utf8')); } catch { return null; } };
function writeJson(f, data) { fs.mkdirSync(path.dirname(f), { recursive: true }); fs.writeFileSync(f, JSON.stringify(data)); }

// Every post a run has read is kept (newest 2000). The search engine blocks after a few
// requests and the post API drops accounts at random; the pool keeps a later run from
// losing good posts it already found.
export const loadPool = () => readJson(POOL) || [];
export function savePool(posts) {
  const byId = new Map(loadPool().map((p) => [p.id, p]));
  for (const p of posts) if (p?.id && p.media?.length) byId.set(p.id, { ...p, rank: undefined });
  const all = [...byId.values()].sort((a, b) => Date.parse(b.created_at || 0) - Date.parse(a.created_at || 0)).slice(0, POOL_MAX);
  writeJson(POOL, all);
  return all.length;
}

// Post links about the idea from web search: DuckDuckGo's HTML page (two requests at most,
// each cached for a day), then the dev-stack SearXNG when it is reachable. DuckDuckGo answers
// 202 with a challenge page once it rate-limits an address; that is reported as `blocked`,
// never as "0 links". Returns { refs: [{id, handle}], notes, blocked, queries }.
export async function webDiscover(idea, { max = 40 } = {}) {
  const refs = new Map(); const notes = []; let blocked = false;
  const add = (list) => { for (const r of list) if (!refs.has(r.id) && refs.size < max) refs.set(r.id, r); };
  const queries = searchQueries(idea);
  for (const [i, q] of queries.entries()) {
    const df = i === 0 ? '' : 'm'; // the idea at any date, the screen type alone only if recent
    const file = path.join(CACHE, 'search', `${slugify(q)}${df ? '-' + df : ''}.json`);
    const hit = readJson(file);
    if (hit && Date.now() - hit.at < SEARCH_TTL_MS) { notes.push(`duckduckgo "${q}": ${hit.refs.length} links (saved today)`); add(hit.refs); continue; }
    if (blocked) continue;
    const r = await get(`https://html.duckduckgo.com/html/?q=${encodeURIComponent(q)}${df ? '&df=' + df : ''}`, { json: false });
    if (r.status === 202 || /anomaly/i.test(String(r.body).slice(0, 20000))) { blocked = true; notes.push(`duckduckgo "${q}": blocked by the search engine (rate limit)`); continue; }
    const found = r.ok && typeof r.body === 'string' ? extractPostRefs(r.body) : [];
    notes.push(`duckduckgo "${q}"${df ? ' (past month)' : ''}: ${r.ok ? found.length + ' links' : 'http ' + r.status}`);
    if (found.length) writeJson(file, { at: Date.now(), refs: found });
    add(found);
    await sleep(1500);
  }
  const s = await get(`${SEARX}/search?q=${encodeURIComponent(queries[0])}&format=json`, { timeout: 5000 });
  if (s.ok && s.body?.results) {
    const found = extractPostRefs(s.body.results.map((x) => x.url).join('\n'));
    notes.push(`searxng: ${found.length} links`); add(found);
  } else notes.push('searxng: not reachable');
  return { refs: [...refs.values()], notes, blocked, queries };
}

export async function saveUrl(url, file, maxMb = 0) {
  const res = await fetch(url, { headers: { 'user-agent': UA }, signal: AbortSignal.timeout(120000) });
  if (!res.ok) throw new Error(`http ${res.status} for ${url}`);
  const len = Number(res.headers.get('content-length') || 0);
  if (maxMb && len > maxMb * 1048576) throw new Error(`${(len / 1048576).toFixed(0)} MB is over the ${maxMb} MB cap`);
  fs.writeFileSync(file, Buffer.from(await res.arrayBuffer()));
  return fs.statSync(file).size;
}
