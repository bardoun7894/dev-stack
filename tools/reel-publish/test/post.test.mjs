import { test } from 'node:test';
import assert from 'node:assert/strict';
import path from 'node:path';
import {
  validatePost, selectPlatforms, scheduleParts, pendingPlatforms, normalizeText, loadPost,
} from '../lib/post.mjs';

const NOW = new Date('2026-10-16T10:00:00Z');
const exists = () => true;
const base = () => ({
  video: '/abs/final.mp4',
  slug: 'day02-xyz',
  schedule: null,
  platforms: {
    youtube: { title: 'عنوان #shorts', description: 'وصف', tags: ['ai'] },
    tiktok: { caption: 'كابشن' },
    facebook_page: { title: 't', description: 'd' },
    facebook_profile: { description: 'd' },
    linkedin: { text: 'نص' },
    drive: {},
  },
});

test('a good post has no errors', () => {
  assert.deepEqual(validatePost(base(), { now: NOW, fileExists: exists }), []);
});

test('missing video file is rejected', () => {
  const errs = validatePost(base(), { now: NOW, fileExists: () => false });
  assert.ok(errs.some((e) => /video file not found/.test(e)), errs.join('|'));
});

test('non-mp4 video is rejected', () => {
  const p = base();
  p.video = '/abs/final.mov';
  assert.ok(validatePost(p, { now: NOW, fileExists: exists }).some((e) => /\.mp4/.test(e)));
});

test('bad slug is rejected', () => {
  for (const slug of ['Day02', 'day 02', 'a/b', '']) {
    const p = base();
    p.slug = slug;
    assert.ok(validatePost(p, { now: NOW, fileExists: exists }).some((e) => /slug/.test(e)), slug);
  }
});

test('youtube title over 100 chars is rejected', () => {
  const p = base();
  p.platforms.youtube.title = 'x'.repeat(101);
  assert.ok(validatePost(p, { now: NOW, fileExists: exists }).some((e) => /youtube.*100/.test(e)));
});

test('youtube title of exactly 100 chars is accepted', () => {
  const p = base();
  p.platforms.youtube.title = 'x'.repeat(100);
  assert.deepEqual(validatePost(p, { now: NOW, fileExists: exists }), []);
});

test('tiktok caption over 2200 chars is rejected', () => {
  const p = base();
  p.platforms.tiktok.caption = 'x'.repeat(2201);
  assert.ok(validatePost(p, { now: NOW, fileExists: exists }).some((e) => /tiktok.*2200/.test(e)));
});

test('schedule in the past is rejected', () => {
  const p = base();
  p.schedule = '2026-10-15T12:00:00Z';
  assert.ok(validatePost(p, { now: NOW, fileExists: exists }).some((e) => /future/.test(e)));
});

test('schedule in the future is accepted', () => {
  const p = base();
  p.schedule = '2026-10-18T12:00:00Z';
  assert.deepEqual(validatePost(p, { now: NOW, fileExists: exists }), []);
});

test('schedule that is not ISO UTC is rejected', () => {
  const p = base();
  p.schedule = 'next tuesday';
  assert.ok(validatePost(p, { now: NOW, fileExists: exists }).some((e) => /schedule/.test(e)));
});

test('unknown platform and empty platforms are rejected', () => {
  const p = base();
  p.platforms.myspace = { text: 'x' };
  assert.ok(validatePost(p, { now: NOW, fileExists: exists }).some((e) => /unknown platform myspace/.test(e)));
  const q = base();
  q.platforms = {};
  assert.ok(validatePost(q, { now: NOW, fileExists: exists }).some((e) => /no platforms/.test(e)));
});

test('arabic text survives untouched', () => {
  const p = base();
  assert.equal(validatePost(p, { now: NOW, fileExists: exists }).length, 0);
  assert.equal(p.platforms.linkedin.text, 'نص');
});

test('selectPlatforms keeps fixed order and honours --only', () => {
  const p = base();
  assert.deepEqual(selectPlatforms(p, null), ['youtube', 'tiktok', 'facebook_page', 'facebook_profile', 'linkedin', 'drive']);
  assert.deepEqual(selectPlatforms(p, ['drive', 'youtube']), ['youtube', 'drive']);
});

test('selectPlatforms rejects platforms not in post.json', () => {
  assert.throws(() => selectPlatforms(base(), ['portfolio']), /not in post.json: portfolio/);
  assert.throws(() => selectPlatforms(base(), ['nope']), /unknown platform: nope/);
});

test('portfolio runs last when present', () => {
  const p = base();
  p.platforms.portfolio = { title: 'عنوان' };
  assert.equal(selectPlatforms(p, null).at(-1), 'portfolio');
});

test('portfolio needs a title', () => {
  const p = base();
  p.platforms.portfolio = {};
  assert.ok(validatePost(p, { now: NOW, fileExists: exists }).some((e) => /portfolio.*title/.test(e)));
});

test('scheduleParts gives UTC date, 24h time and 12h label', () => {
  assert.deepEqual(scheduleParts('2026-10-18T12:00:00Z'), {
    date: '2026-10-18', time24: '12:00', time12: '12:00 PM', iso: '2026-10-18T12:00:00.000Z',
  });
  assert.equal(scheduleParts('2026-10-18T00:30:00Z').time12, '12:30 AM');
});

test('pendingPlatforms skips only platforms already ok', () => {
  const results = {
    youtube: { ok: true, url: 'u', error: null, at: 't' },
    tiktok: { ok: false, url: null, error: 'boom', at: 't' },
  };
  assert.deepEqual(pendingPlatforms(results, ['youtube', 'tiktok', 'linkedin']), ['tiktok', 'linkedin']);
});

test('normalizeText is NFC and collapses whitespace', () => {
  assert.equal(normalizeText('  a \n\t b  '), 'a b');
  assert.equal(normalizeText('é'), 'é');
});

test('loadPost resolves a relative video path against the post.json directory', async () => {
  const { writeFileSync, mkdtempSync } = await import('node:fs');
  const os = await import('node:os');
  const dir = mkdtempSync(path.join(os.tmpdir(), 'rp-'));
  const file = path.join(dir, 'post.json');
  const p = base();
  p.video = 'final.mp4';
  writeFileSync(file, JSON.stringify(p));
  const loaded = loadPost(file, { now: NOW, fileExists: (f) => f === path.join(dir, 'final.mp4') });
  assert.equal(loaded.video, path.join(dir, 'final.mp4'));
  assert.equal(loaded.dir, dir);
});

test('loadPost throws with all errors joined on bad JSON', () => {
  assert.throws(() => loadPost('/nonexistent/post.json', { now: NOW, fileExists: exists }), /cannot read/);
});
