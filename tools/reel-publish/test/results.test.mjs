import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { readResults, recordResult } from '../lib/results.mjs';

const tmp = () => fs.mkdtempSync(path.join(os.tmpdir(), 'rp-res-'));

test('readResults returns {} when results.json does not exist', () => {
  assert.deepEqual(readResults(tmp()), {});
});

test('recordResult writes ok and keeps earlier platforms', () => {
  const dir = tmp();
  recordResult(dir, 'youtube', { ok: true, url: 'https://youtube.com/shorts/abc', error: null });
  recordResult(dir, 'tiktok', { ok: false, url: null, error: 'boom' });
  const r = readResults(dir);
  assert.equal(r.youtube.ok, true);
  assert.equal(r.youtube.url, 'https://youtube.com/shorts/abc');
  assert.equal(r.tiktok.ok, false);
  assert.equal(r.tiktok.error, 'boom');
  assert.match(r.tiktok.at, /^\d{4}-\d{2}-\d{2}T/);
});

test('recordResult replaces a failed platform with a later ok result', () => {
  const dir = tmp();
  recordResult(dir, 'linkedin', { ok: false, url: null, error: 'x' });
  recordResult(dir, 'linkedin', { ok: true, url: null, error: null });
  assert.equal(readResults(dir).linkedin.ok, true);
});

test('recordResult never overwrites an ok platform with a failure', () => {
  const dir = tmp();
  recordResult(dir, 'drive', { ok: true, url: 'u', error: null });
  recordResult(dir, 'drive', { ok: false, url: null, error: 'later' });
  assert.equal(readResults(dir).drive.ok, true);
  assert.equal(readResults(dir).drive.url, 'u');
});

test('no leftover tmp file after a write', () => {
  const dir = tmp();
  recordResult(dir, 'drive', { ok: true, url: null, error: null });
  assert.deepEqual(fs.readdirSync(dir).sort(), ['results.json']);
});
