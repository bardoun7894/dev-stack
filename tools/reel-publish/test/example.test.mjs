import { test } from 'node:test';
import assert from 'node:assert/strict';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { loadPost, selectPlatforms } from '../lib/post.mjs';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

test('post.example.json validates with its fixture video', () => {
  const post = loadPost(path.join(ROOT, 'post.example.json'));
  assert.equal(post.video, path.join(ROOT, 'fixtures/example.mp4'));
  assert.equal(selectPlatforms(post, null).at(-1), 'portfolio');
});
