import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { execFileSync } from 'node:child_process';

const CLI = path.resolve(import.meta.dirname, '../publish.mjs');

function fixture(overrides = {}) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'rp-cli-'));
  const video = path.join(dir, 'final.mp4');
  fs.writeFileSync(video, 'not really a video');
  const post = {
    video: 'final.mp4',
    slug: 'day99-test',
    schedule: null,
    platforms: { drive: {}, linkedin: { text: 'نص' } },
    ...overrides,
  };
  const file = path.join(dir, 'post.json');
  fs.writeFileSync(file, JSON.stringify(post));
  return { dir, file };
}

test('plan mode (no --yes) prints the plan, exits 0 and writes no results.json', () => {
  const { dir, file } = fixture();
  const out = execFileSync(process.execPath, [CLI, file], { encoding: 'utf8' });
  assert.match(out, /PLAN/);
  assert.match(out, /drive/);
  assert.match(out, /linkedin/);
  assert.match(out, /nothing posted/i);
  assert.equal(fs.existsSync(path.join(dir, 'results.json')), false);
});

test('plan mode prints the schedule when one is set', () => {
  const { file } = fixture({ schedule: '2999-01-01T12:00:00Z' });
  const out = execFileSync(process.execPath, [CLI, file], { encoding: 'utf8' });
  assert.match(out, /2999-01-01T12:00:00\.000Z/);
});

test('an invalid post.json exits 2 with the errors listed', () => {
  const { file } = fixture({ slug: 'BAD SLUG' });
  let err;
  try {
    execFileSync(process.execPath, [CLI, file], { encoding: 'utf8', stdio: 'pipe' });
  } catch (e) {
    err = e;
  }
  assert.equal(err.status, 2);
  assert.match(err.stderr, /slug must match/);
});
