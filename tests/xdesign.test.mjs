// node --test tests/xdesign.test.mjs — pure logic of the xDesignSkill CLI (no network, no ffmpeg).
import test from 'node:test';
import assert from 'node:assert/strict';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const { parsePostRef, cleanHandle, parseHandleList, normalizePost, ideaTerms, scorePost, rankPosts, quantize, slugify } =
  await import(join(ROOT, 'skills', 'xDesignSkill', 'scripts', 'xdesign.mjs'));

const NOW = Date.parse('2026-11-23T12:00:00Z');
const post = (text, daysAgo = 1, extra = {}) => ({
  id: String(Math.round(daysAgo * 1000)), handle: 'h', text, created_at: new Date(NOW - daysAgo * 864e5).toISOString(),
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

test('recency and reach order matched posts but never make an unrelated post match', () => {
  const terms = ideaTerms('bank dashboard');
  const viral = scorePost(post('Puzzle game', 0, { views: 5_000_000 }), terms, NOW);
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
});

test('normalizePost reads the syndication shape (single-post fallback)', () => {
  const p = normalizePost({
    id_str: '2', text: 'Care &amp; Hub https://t.co/abc', created_at: '2026-11-22T16:57:40.000Z', favorite_count: 179, user: { screen_name: 'b', name: 'B' },
    mediaDetails: [{ type: 'photo', media_url_https: 'https://pbs.twimg.com/media/Y.jpg', original_info: { width: 4096, height: 3072 } }],
  });
  assert.equal(p.url, 'https://x.com/b/status/2');
  assert.equal(p.text, 'Care & Hub');
  assert.deepEqual(p.media, [{ type: 'photo', url: 'https://pbs.twimg.com/media/Y.jpg?name=orig', width: 4096, height: 3072 }]);
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
