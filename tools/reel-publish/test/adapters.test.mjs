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
