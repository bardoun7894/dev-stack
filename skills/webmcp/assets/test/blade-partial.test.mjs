// Runs the script from assets/blade/webmcp.blade.php against a stub document.modelContext and fetch.
// node --test skills/webmcp/assets/test/blade-partial.test.mjs
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';

const BLADE = join(dirname(fileURLToPath(import.meta.url)), '..', 'blade', 'webmcp.blade.php');

function run(tools) {
  const src = readFileSync(BLADE, 'utf8').match(/<script>([\s\S]*)<\/script>/)[1]
    .replace('@json($tools)', JSON.stringify(tools))
    .replace("'{{ csrf_token() }}'", "'csrf-test'");
  const registered = [];
  const fetches = [];
  const ctx = {
    document: { modelContext: { registerTool: (t) => { registered.push(t); return Promise.resolve(); } },
                querySelector: () => null },
    window: { addEventListener() {} },
    fetch: async (url, opts) => { fetches.push({ url, opts }); return { ok: true, text: async () => '{}' }; },
    AbortController, URLSearchParams, Promise, console, Object, JSON, Error, String, encodeURIComponent,
  };
  vm.runInNewContext(src, ctx);
  return { registered, fetches, byName: (n) => registered.find((t) => t.name === n) };
}

const tool = (name, method, url, annotations) => ({ name, description: name, inputSchema: { type: 'object' }, method, url, ...(annotations ? { annotations } : {}) });

test('non-GET tools default to consequentialHint: true, GET tools do not', () => {
  const r = run([tool('read', 'GET', '/a'), tool('add', 'POST', '/b'), tool('del', 'delete', '/c/{id}'),
                 tool('noask', 'PUT', '/d', { consequentialHint: false })]);
  assert.equal(r.byName('read').annotations.consequentialHint, undefined);
  assert.equal(r.byName('add').annotations.consequentialHint, true);
  assert.equal(r.byName('del').annotations.consequentialHint, true);
  assert.equal(r.byName('noask').annotations.consequentialHint, false); // explicit annotation wins
});

test('non-GET sends JSON with the CSRF token', async () => {
  const r = run([tool('add', 'POST', '/cart')]);
  await r.byName('add').execute({ courseId: 'c1' }, {});
  const { opts } = r.fetches[0];
  assert.equal(opts.method, 'POST');
  assert.equal(opts.headers['X-CSRF-TOKEN'], 'csrf-test');
  assert.equal(opts.body, '{"courseId":"c1"}');
});
