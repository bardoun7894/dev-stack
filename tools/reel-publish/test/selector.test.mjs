import { test } from 'node:test';
import assert from 'node:assert/strict';
import { splitSelector, engineExpression } from '../lib/selector.mjs';

test('splitSelector splits plain alternatives', () => {
  assert.deepEqual(splitSelector('a, b'), ['a', 'b']);
});

test('splitSelector keeps commas inside quotes, brackets and parens', () => {
  assert.deepEqual(splitSelector('button:has-text("Post, now"), text=Share'), ['button:has-text("Post, now")', 'text=Share']);
  assert.deepEqual(splitSelector('[data-x="a,b"], :is(p, q)'), ['[data-x="a,b"]', ':is(p, q)']);
});

test('engineExpression is a syntactically valid expression', () => {
  assert.doesNotThrow(() => new Function(`return ${engineExpression(['text=Foo'], 0, null, 'el')}`));
});
