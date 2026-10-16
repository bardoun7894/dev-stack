import { test } from 'node:test';
import assert from 'node:assert/strict';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const DIR = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../adapters');
const NAMES = ['youtube', 'tiktok', 'facebook_page', 'facebook_profile', 'linkedin', 'drive', 'portfolio'];

for (const name of NAMES) {
  test(`adapter ${name} imports and exposes run()`, async () => {
    const mod = await import(path.join(DIR, `${name}.mjs`));
    assert.equal(mod.default.name, name);
    assert.equal(typeof mod.default.run, 'function');
  });
}

test('facebook adapters refuse a scheduled post instead of posting now', async () => {
  const post = { schedule: '2099-01-01T12:00:00Z', video: 'x.mp4', slug: 's' };
  for (const name of ['facebook_page', 'facebook_profile']) {
    const a = (await import(`../adapters/${name}.mjs`)).default;
    let opened = false;
    const ctx = { post, platform: { title: 't', description: 'd' }, mode: 'publish', runDir: '/tmp', log() {},
      results: {}, newPage: async () => { opened = true; throw new Error('should not open a page'); } };
    await assert.rejects(a.run(ctx), /scheduling not wired|no scheduler/);
    assert.equal(opened, false);
  }
});
