import { test } from 'node:test';
import assert from 'node:assert/strict';
import { tiktokIdFromUrl, addTiktokEntry, serializeSocialVideos } from '../lib/portfolio.mjs';

const URL1 = 'https://www.tiktok.com/@mbardouni.dev/video/7692555839378394389';
const URL2 = 'https://www.tiktok.com/@mbardouni.dev/video/7000000000000000001';
const doc = () => ({
  _note: 'keep me',
  tiktok: [{ url: URL1, title: 'old', thumb: '/content/social/x.jpg' }],
  instagram: [],
});

test('tiktokIdFromUrl extracts the numeric id', () => {
  assert.equal(tiktokIdFromUrl(URL1), '7692555839378394389');
  assert.equal(tiktokIdFromUrl('https://www.tiktok.com/@x/photo/123'), null);
  assert.equal(tiktokIdFromUrl(null), null);
});

test('addTiktokEntry prepends a new video and keeps _note and instagram', () => {
  const { doc: out, added } = addTiktokEntry(doc(), { url: URL2, title: 'جديد' });
  assert.equal(added, true);
  assert.deepEqual(out.tiktok.map((e) => e.url), [URL2, URL1]);
  assert.deepEqual(out.tiktok[0], { url: URL2, title: 'جديد' });
  assert.equal(out._note, 'keep me');
  assert.deepEqual(out.instagram, []);
});

test('addTiktokEntry does not duplicate an existing url', () => {
  const { doc: out, added } = addTiktokEntry(doc(), { url: URL1, title: 'new title' });
  assert.equal(added, false);
  assert.equal(out.tiktok.length, 1);
  assert.equal(out.tiktok[0].title, 'old');
});

test('addTiktokEntry does not mutate its input', () => {
  const input = doc();
  addTiktokEntry(input, { url: URL2, title: 't' });
  assert.equal(input.tiktok.length, 1);
});

test('addTiktokEntry works when the tiktok array is missing', () => {
  const { doc: out } = addTiktokEntry({ _note: 'n' }, { url: URL2, title: 't' });
  assert.deepEqual(out.tiktok, [{ url: URL2, title: 't' }]);
});

test('serializeSocialVideos keeps Arabic readable and ends with a newline', () => {
  const s = serializeSocialVideos({ tiktok: [{ url: URL2, title: 'مرحبا' }] });
  assert.match(s, /مرحبا/);
  assert.ok(s.endsWith('\n'));
  assert.match(s, /\n  "tiktok": \[/);
});
