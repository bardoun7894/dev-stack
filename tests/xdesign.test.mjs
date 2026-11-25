// node --test tests/xdesign.test.mjs — pure logic of the xDesignSkill CLI (no network, no ffmpeg).
import test from 'node:test';
import assert from 'node:assert/strict';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const S = join(ROOT, 'skills', 'xDesignSkill', 'scripts');
// Before the first import: net.mjs reads the cache folder once, when it loads. Without this the
// pool test would write its fixtures into the real ~/.cache/xdesign.
process.env.XDESIGN_CACHE = mkdtempSync(join(tmpdir(), 'xdesign-test-'));
const { parsePostRef, extractPostRefs, searchQueries, cleanHandle, parseHandleList, normalizePost, ideaTerms, quality, scorePost, rankPosts, quantize, slugify } = await import(join(S, 'xdesign.mjs'));
const { galleryHtml } = await import(join(S, 'media.mjs'));
const { loadPool, savePool } = await import(join(S, 'net.mjs'));

const NOW = Date.parse('2026-11-23T12:00:00Z');
const post = (text, daysAgo = 1, extra = {}) => ({
  id: String(Math.round(daysAgo * 1000)), handle: 'h_design', text, created_at: new Date(NOW - daysAgo * 864e5).toISOString(),
  likes: 10, views: 1000, media: [{ type: 'photo', url: 'u', width: 100, height: 100 }], ...extra,
});

test('parsePostRef reads x.com and twitter.com links with tracking params, and bare ids', () => {
  assert.deepEqual(parsePostRef('https://x.com/uifoysal/status/2124547874956677451?a=XY_F677L0ub3uXRa2pM&s=20'), { id: '2124547874956677451', handle: 'uifoysal' });
  assert.deepEqual(parsePostRef('https://twitter.com/a_b/status/123456789/photo/1'), { id: '123456789', handle: 'a_b' });
  assert.deepEqual(parsePostRef('2124547874956677451'), { id: '2124547874956677451', handle: null });
  assert.equal(parsePostRef('https://example.com/x/status/1'), null);
  assert.equal(parsePostRef('hello'), null);
});

test('cleanHandle accepts @name and profile links, rejects anything that is not a handle', () => {
  assert.equal(cleanHandle('@uifoysal'), 'uifoysal');
  assert.equal(cleanHandle('https://x.com/uifoysal?s=20'), 'uifoysal');
  assert.equal(cleanHandle('not a handle'), null);
  assert.equal(cleanHandle('../../etc/passwd'), null);
  assert.equal(cleanHandle('waytoolonghandlename'), null);
});

test('parseHandleList drops comments, blanks and case-insensitive duplicates', () => {
  assert.deepEqual(parseHandleList('# seed\nuifoysal  # dashboards\n\n@ui8\nUIFoysal\nbad handle!\n'), ['uifoysal', 'ui8', 'bad']);
});

test('ideaTerms splits subject words from the screen type and drops filler words', () => {
  assert.deepEqual(ideaTerms('Transport fleet dashboard UI design'), { subject: ['transport', 'fleet'], types: ['dashboard'] });
  assert.deepEqual(ideaTerms('restaurant app'), { subject: ['restaurant'], types: [] });
  assert.deepEqual(ideaTerms('admin panel for clinics').types, ['dashboard']);
});

test('a post of another project type still matches on the screen type, below a subject match', () => {
  const terms = ideaTerms('transport fleet dashboard');
  const other = scorePost(post('Mediora – AI Healthcare & Patient Care Dashboard UI/UX Design'), terms, NOW);
  const same = scorePost(post('Fleet tracking dashboard for transport companies'), terms, NOW);
  const none = scorePost(post('Puzzle Game Mobile App UI/UX Design'), terms, NOW);
  assert.equal(other.matched, 2);
  assert.deepEqual(other.typeHits, ['dashboard']);
  assert.equal(same.matched, 8);
  assert.equal(none.matched, 0);
  assert.ok(same.score > other.score && other.score > none.score);
});

test('sibling words of the screen type match, substrings inside other words do not', () => {
  const terms = ideaTerms('clinic dashboard');
  assert.equal(scorePost(post('CRM admin panel kit'), terms, NOW).matched, 2);
  assert.equal(scorePost(post('Scrambled eggs recipe'), terms, NOW).matched, 0); // "crm" is not in "scrambled" as a word start
  assert.equal(scorePost(post('Clinics booking flow'), terms, NOW).subjectHits.length, 1); // plural
});

test('rankPosts drops unmatched posts and posts without media, honours --days and --all', () => {
  const posts = [
    post('Insurance Management Dashboard UI Design', 4),
    post('Insurance dashboard, older', 50),
    post('Puzzle game', 1),
    post('Healthcare dashboard without media', 1, { media: [] }),
  ];
  const ranked = rankPosts(posts, 'insurance dashboard', { now: NOW });
  assert.deepEqual(ranked.map((p) => p.text), ['Insurance Management Dashboard UI Design', 'Insurance dashboard, older']);
  assert.equal(rankPosts(posts, 'insurance dashboard', { now: NOW, days: 30 }).length, 1);
  assert.equal(rankPosts(posts, 'insurance dashboard', { now: NOW, all: true }).length, 3);
});

test('recency and quality order matched posts but never make an unrelated post match', () => {
  const terms = ideaTerms('bank dashboard');
  const viral = scorePost(post('Puzzle game', 0, { likes: 90000, bookmarks: 50000 }), terms, NOW);
  assert.equal(viral.matched, 0);
  const fresh = scorePost(post('Bank dashboard', 1), terms, NOW);
  const old = scorePost(post('Bank dashboard', 300), terms, NOW);
  assert.ok(fresh.score > old.score);
});

test('normalizePost reads an FxTwitter status: original photo, best mp4 variant', () => {
  const p = normalizePost({
    id: '1', url: 'https://x.com/a/status/1', text: ' Dash ', author: { screen_name: 'a', name: 'A' }, created_timestamp: 1795366660, likes: 5, views: 9,
    media: { all: [
      { type: 'photo', url: 'https://pbs.twimg.com/media/X.jpg?name=orig', width: 4096, height: 3072 },
      { type: 'video', url: 'https://v/low.mp4', duration: 23.2, width: 1920, height: 1080, variants: [
        { content_type: 'application/x-mpegURL', url: 'https://v/pl.m3u8' },
        { content_type: 'video/mp4', bitrate: 832000, url: 'https://v/low.mp4' },
        { content_type: 'video/mp4', bitrate: 2176000, url: 'https://v/high.mp4' },
      ] },
    ] },
  });
  assert.equal(p.handle, 'a');
  assert.equal(p.text, 'Dash');
  assert.equal(p.created_at, '2026-11-22T16:57:40.000Z');
  assert.deepEqual(p.media.map((m) => [m.type, m.url]), [['photo', 'https://pbs.twimg.com/media/X.jpg?name=orig'], ['video', 'https://v/high.mp4']]);
  assert.equal(p.media[0].thumb, 'https://pbs.twimg.com/media/X.jpg?name=small');
});

test('normalizePost reads the syndication shape (single-post fallback)', () => {
  const p = normalizePost({
    id_str: '2', text: 'Care &amp; Hub https://t.co/abc', created_at: '2026-11-22T16:57:40.000Z', favorite_count: 179, user: { screen_name: 'b', name: 'B' },
    mediaDetails: [{ type: 'photo', media_url_https: 'https://pbs.twimg.com/media/Y.jpg', original_info: { width: 4096, height: 3072 } }],
  });
  assert.equal(p.url, 'https://x.com/b/status/2');
  assert.equal(p.text, 'Care & Hub');
  assert.deepEqual(p.media, [{ type: 'photo', url: 'https://pbs.twimg.com/media/Y.jpg?name=orig', thumb: 'https://pbs.twimg.com/media/Y.jpg?name=small', width: 4096, height: 3072 }]);
});

test('quantize returns the dominant colors with shares, merging near-identical ones', () => {
  const px = [];
  for (let i = 0; i < 60; i++) px.push(255, 255, 255);
  for (let i = 0; i < 30; i++) px.push(30, 90, 200);
  for (let i = 0; i < 10; i++) px.push(33, 92, 203); // JPEG noise around the same blue
  const pal = quantize(Buffer.from(px));
  assert.equal(pal.length, 2);
  assert.deepEqual(pal[0], { hex: '#ffffff', share: 60 });
  assert.equal(pal[1].share, 40);
  assert.match(pal[1].hex, /^#1e5ac8$/);
});

test('slugify makes a safe folder part', () => {
  assert.equal(slugify('Transport & Fleet / Dashboard!'), 'transport-fleet-dashboard');
  assert.equal(slugify('داشبورد'), 'posts');
});

test('quality rewards likes and saves, capped at 3, and works without a saves count', () => {
  assert.equal(quality({ likes: 0, bookmarks: 0 }), 0);
  assert.equal(quality({ likes: 99, bookmarks: 99 }), 2);
  assert.equal(quality({ likes: 999, bookmarks: null }), 3);
  assert.equal(quality({ likes: 9_999_999, bookmarks: 9_999_999 }), 3);
  assert.ok(quality({ likes: 399, bookmarks: 443 }) > quality({ likes: 15, bookmarks: 7 }));
});

test('a well received post of another project type passes an exact match nobody liked, not a liked one', () => {
  const strong = post('Healthcare analytics dashboard', 5, { id: 'strong', likes: 900, bookmarks: 800 });
  const weak = post('Fleet dashboard', 5, { id: 'weak', likes: 1, bookmarks: 0 });
  const liked = post('Fleet dashboard', 5, { id: 'liked', likes: 100, bookmarks: 50 });
  assert.deepEqual(rankPosts([weak, strong], 'fleet dashboard', { now: NOW }).map((p) => p.id), ['strong', 'weak']);
  assert.deepEqual(rankPosts([strong, liked], 'fleet dashboard', { now: NOW }).map((p) => p.id), ['liked', 'strong']);
});

test('rankPosts drops duplicate ids, caps posts per author, filters by likes, sorts on request', () => {
  const posts = [
    post('Bank dashboard one', 1, { id: 'a1', handle: 'A_ui', likes: 50 }),
    post('Bank dashboard two', 2, { id: 'a2', handle: 'a_UI', likes: 40 }),
    post('Bank dashboard three', 3, { id: 'a3', handle: 'A_ui', likes: 30 }),
    post('Bank dashboard other', 4, { id: 'b1', handle: 'B_ui', likes: 5 }),
    post('Bank dashboard one', 1, { id: 'a1', handle: 'A_ui', likes: 50 }),
  ];
  assert.equal(rankPosts(posts, 'bank dashboard', { now: NOW }).length, 4);
  assert.deepEqual(rankPosts(posts, 'bank dashboard', { now: NOW, perAuthor: 2 }).map((p) => p.id), ['a1', 'a2', 'b1']);
  assert.deepEqual(rankPosts(posts, 'bank dashboard', { now: NOW, minLikes: 35 }).map((p) => p.id), ['a1', 'a2']);
  assert.deepEqual(rankPosts(posts, 'bank dashboard', { now: NOW, sort: 'recent' }).map((p) => p.id), ['a1', 'a2', 'a3', 'b1']);
});

test('extractPostRefs finds post links in a search page, encoded or not, once each', () => {
  const html = `<a href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fx.com%2FIamMuhammadMuiz%2Fstatus%2F2095957126229148112&amp;rut=1">a</a>
    <a href="https://x.com/IamMuhammadMuiz/status/2095957126229148112">again</a>
    <a href="https://twitter.com/uifoysal/status/2123467455419007426?s=20">b</a>
    <a href="https://x.com/i/status/111111111111">not an author link</a> <a href="https://x.com/search?q=dashboard">search</a>`;
  assert.deepEqual(extractPostRefs(html), [{ id: '2095957126229148112', handle: 'IamMuhammadMuiz' }, { id: '2123467455419007426', handle: 'uifoysal' }]);
  assert.deepEqual(extractPostRefs('nothing here'), []);
});

test('searchQueries asks for the idea, and for the screen type alone when there is a subject', () => {
  assert.deepEqual(searchQueries('transport fleet dashboard'), ['site:x.com transport fleet dashboard UI design', 'site:x.com "dashboard" UI UX design']);
  assert.deepEqual(searchQueries('dashboard'), ['site:x.com dashboard UI design']);
  assert.deepEqual(searchQueries('restaurant menu'), ['site:x.com restaurant menu UI design']);
});

test('galleryHtml numbers the cards, links the post, and escapes post text', () => {
  const html = galleryHtml('fleet <dash>', [{ n: 1, url: 'https://x.com/a/status/1', handle: 'a', text: '<script>alert(1)</script> "Fleet"', created_at: '2026-11-01T00:00:00.000Z', likes: 1500, bookmarks: 20, views: null,
    media: [{ type: 'photo', url: 'u', thumb: 'https://pbs.twimg.com/media/X.jpg?name=small' }], thumbFile: 'thumbs/01.jpg', rank: { subjectHits: ['fleet'], typeHits: ['dashboard'], score: 7.1 } }]);
  assert.ok(html.includes('<h1>fleet &lt;dash&gt;</h1>'));
  assert.ok(html.includes('src="thumbs/01.jpg"'));
  assert.ok(html.includes('href="https://x.com/a/status/1"'));
  assert.ok(html.includes('&lt;script&gt;alert(1)&lt;/script&gt; &quot;Fleet&quot;'));
  assert.ok(!html.includes('<script>'));
  assert.ok(html.includes('1.5k likes') && html.includes('? views') && html.includes('match: fleet, type: dashboard'));
});

test('the pool keeps posts across runs: merged by id, newest copy wins, posts without media left out', () => {
  assert.deepEqual(loadPool(), []);
  assert.equal(savePool([post('Fleet dashboard', 3, { id: 'p1', likes: 5 }), post('No media', 1, { id: 'p2', media: [] })]), 1);
  assert.equal(savePool([post('Fleet dashboard', 3, { id: 'p1', likes: 80, rank: { score: 9 } }), post('Bank dashboard', 1, { id: 'p3' })]), 2);
  const pool = loadPool();
  assert.deepEqual(pool.map((p) => p.id), ['p3', 'p1']); // newest first
  assert.equal(pool[1].likes, 80);
  assert.equal(pool[1].rank, undefined);
  assert.deepEqual(rankPosts(pool, 'fleet dashboard', { now: NOW }).map((p) => p.id), ['p1', 'p3']);
});

test('xQuery asks X for UI/UX media posts with a likes floor, without replies', async () => {
  const { xQuery } = await import(join(S, 'xsearch.mjs'));
  assert.equal(xQuery(' fleet dashboard '), 'fleet dashboard (UI OR UX OR Figma) filter:media min_faves:20 -filter:replies');
  assert.equal(xQuery('restaurant POS order management dashboard', 0), '(restaurant OR pos) dashboard (UI OR UX OR Figma) filter:media -filter:replies');
  assert.equal(xQuery('order management dashboard'), '(order OR management) dashboard (UI OR UX OR Figma) filter:media min_faves:20 -filter:replies');
  assert.equal(xQuery('dashboard'), 'dashboard (UI OR UX OR Figma) filter:media min_faves:20 -filter:replies');
  assert.equal(xQuery('banking app ui'), 'banking filter:media min_faves:20 -filter:replies');
});

test('posts that never name design work are dropped, unless --all', () => {
  const posts = [
    post('KAV loves Solana, the biggest order book dashboard of 2030', 1, { id: 'coin', handle: 'KavianCoin', likes: 9000 }),
    post('Restaurant order dashboard UI, light and dark', 2, { id: 'ui', handle: 'someone' }),
    post('Restaurant Revenue Dashboard (Light & Dark)', 2, { id: 'by-designer', handle: 'abu_uiuxdesign' }),
  ];
  assert.deepEqual(rankPosts(posts, 'restaurant order dashboard', { now: NOW }).map((p) => p.id), ['ui', 'by-designer']);
  assert.equal(rankPosts(posts, 'restaurant order dashboard', { now: NOW, all: true }).length, 3);
});

test('only the opening of a post counts for the match', () => {
  const terms = ideaTerms('restaurant pos dashboard');
  const thread = post('Top 21 web project ideas to build your portfolio. ' + 'Ideas list. '.repeat(40) + '19. Restaurant POS dashboard UI', 1);
  assert.equal(scorePost(thread, terms, NOW).matched, 0);
  assert.equal(scorePost(post('Restaurant POS dashboard UI', 1), terms, NOW).matched, 8);
});

test('save: a 5xx download is retried; a post whose files all failed is not recorded and is saved on the next run', async () => {
  const { createServer } = await import('node:http');
  const { readFileSync } = await import('node:fs');
  const { savePosts } = await import(join(S, 'save.mjs'));
  const hits = new Map(); let bOk = false;
  const srv = createServer((req, res) => {
    const n = (hits.get(req.url) || 0) + 1; hits.set(req.url, n);
    if (req.url === '/a.jpg' && n === 1) { res.writeHead(503); return res.end(); }
    if (req.url === '/b.jpg' && !bOk) { res.writeHead(404); return res.end(); }
    res.writeHead(200, { 'content-type': 'image/jpeg' }); res.end('not-really-a-jpeg');
  });
  await new Promise((r) => srv.listen(0, '127.0.0.1', r));
  const base = `http://127.0.0.1:${srv.address().port}`;
  const mk = (id, file) => post('dashboard UI', 1, { id, handle: 'h_design', url: `https://x.com/h_design/status/${id}`, media: [{ type: 'photo', url: `${base}/${file}`, width: 100, height: 100 }] });
  const dir = mkdtempSync(join(tmpdir(), 'xdesign-save-'));
  const logs = []; const log = (s) => logs.push(s);
  try {
    const first = await savePosts([mk('111', 'a.jpg'), mk('222', 'b.jpg')], 'test', dir, { log });
    assert.deepEqual([first.added, first.failed], [1, 1]);
    assert.equal(hits.get('/a.jpg'), 2, 'the 503 was retried once');
    assert.equal(hits.get('/b.jpg'), 1, 'a 404 is not retried');
    assert.ok(logs.some((l) => /FAILED .*222/.test(l)));
    assert.deepEqual(JSON.parse(readFileSync(join(dir, 'manifest.json'), 'utf8')).posts.map((p) => p.id), ['111']);
    bOk = true;
    const second = await savePosts([mk('111', 'a.jpg'), mk('222', 'b.jpg')], 'test', dir, { log });
    assert.deepEqual([second.added, second.failed], [1, 0]);
    const m = JSON.parse(readFileSync(join(dir, 'manifest.json'), 'utf8'));
    assert.deepEqual(m.posts.map((p) => [p.n, p.id]), [[1, '111'], [2, '222']]);
  } finally { srv.close(); }
});

test('session import takes only x.com / twitter.com cookies and needs the session cookie', async () => {
  const { importSession } = await import(join(S, 'xsearch.mjs'));
  await assert.rejects(importSession({ cookies: [{ domain: '.evil.com', name: 'auth_token', value: 'v' }] }), /no X session cookie/);
  await assert.rejects(importSession({ cookies: [{ domain: '.x.com', name: 'ct0', value: 'v' }] }), /no X session cookie/);
  await assert.rejects(importSession({}), /no X session cookie/);
});
