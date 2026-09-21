// node --test tests/  — policy of the Jev browser agent (no browser, no network)
import test from 'node:test';
import assert from 'node:assert/strict';
import {
  compactSnapshot, buildStepQuestions, buildStepState, buildJudgeState, decideStep, validateAnswer,
  stuckFromHistory, actionSpace, personaData, judgeFlow, PERSONAS,
} from '../skills/jev/scripts/browse-core.mjs';
import { parseText, fieldText } from '../skills/jev/scripts/text-helper.mjs';

// The shape snapshot.js returns: every element carries its own viewport index, and scroll/wait are pseudo
// actions the page offers only when they are possible.
const ACTIONS = [
  { index: '1', kind: 'click', role: 'link', label: 'Home', href: '/index.html', external: false },
  { index: '2', kind: 'click', role: 'link', label: 'Telegram', href: 'https://t.me/x', external: true },
  { index: '3', kind: 'click', role: 'button', label: 'Send message', inForm: true },
  { index: '4', kind: 'click', role: 'button', label: 'Menu', inForm: false },
  { index: '5', kind: 'fill', role: 'textbox', type: 'email', label: 'Email', value: '', empty: true },
  { index: '6', kind: 'fill', role: 'textbox', type: 'password', label: 'Password', value: '', empty: true, secret: true },
  { index: '7', kind: 'select', role: 'combobox', label: 'Country', value: 'Morocco', options: [{ value: 'ma', label: 'Morocco' }, { value: 'fr', label: 'France' }] },
  { kind: 'scroll', id: 'SCROLL_DOWN', delta: 560 },
];
const OBS = {
  url: 'https://x.test/login', title: 'Login', text: 'Sign in', actions: ACTIONS,
  scroll: { y: 0, viewport: 900, height: 2400 }, omitted: 0, guards: {}, marker: 'm', pageKey: 'k', hasLayout: true,
};
const ops = (q) => Object.keys(q.operation.criteria).sort();
const DATA = { email: 'a@b.co', password: 'pw' };

test('read-only by default: no form submit, no dropdown change, no typing, never off-site links', () => {
  // mbardouni.dev 2026-09-19: a "find how to hire" flow clicked the live contact form's Send button (the
  // backend rejected the empty POST), and the community flow crashed on tg:// and wandered to t.me.
  const q = buildStepQuestions(OBS, {});
  assert.deepEqual(ops(q), ['BLOCKED', 'CLICK', 'DONE', 'SCROLL_DOWN', 'WAIT']);
  assert.deepEqual(Object.keys(q.click_target.criteria).sort(), ['1', '4']);
  assert.equal(q.type_text_target, undefined);
  assert.equal(q.select_target, undefined);
});

test('data (or --allow-submit) unlocks submit, typing and dropdowns', () => {
  const q = buildStepQuestions(OBS, DATA);
  assert.deepEqual(ops(q), ['BLOCKED', 'CLICK', 'DONE', 'SCROLL_DOWN', 'SELECT', 'TYPE_TEXT', 'WAIT']);
  assert.deepEqual(Object.keys(q.click_target.criteria).sort(), ['1', '3', '4']);
  assert.deepEqual(Object.keys(q.type_text_target.criteria).sort(), ['5', '6']);
  // Each dropdown option is its own target, so the model never writes a value — it picks an observed one.
  assert.deepEqual(Object.keys(q.select_target.criteria).sort(), ['7:1', '7:2']);
  assert.deepEqual(ops(buildStepQuestions(OBS, {}, { allowSubmit: true })), ops(q));
});

test('--autofill unlocks typing without data, but not form submits', () => {
  const q = buildStepQuestions(OBS, {}, { autofill: true });
  assert.ok(ops(q).includes('TYPE_TEXT'));
  assert.deepEqual(Object.keys(q.click_target.criteria).sort(), ['1', '4']);
  assert.equal(q.select_target, undefined);
});

test('with --data only EMPTY fields are typeable; --autofill can retype a filled one', () => {
  // Adversarial run 2026-09-21: TYPE_TEXT was offered on the already-filled Email, --data had no value
  // question for it, and the flow ended at `no_value` after one step — depending on which field Jev picked.
  const filled = { ...OBS, actions: ACTIONS.map((a) => (a.index === '5' ? { ...a, value: 'a@b.co', empty: false } : a)) };
  assert.deepEqual(Object.keys(buildStepQuestions(filled, DATA).type_text_target.criteria), ['6']);
  assert.deepEqual(Object.keys(buildStepQuestions(filled, {}, { autofill: true }).type_text_target.criteria).sort(), ['5', '6']);
  // Every offered TYPE_TEXT target has a value question to answer it.
  const q = buildStepQuestions(filled, DATA);
  for (const i of Object.keys(q.type_text_target.criteria)) assert.ok(q[`value_${i}`], `value_${i} missing`);
});

test('one request carries the operation head and every target head (speculative fan-out)', () => {
  const q = buildStepQuestions(OBS, DATA);
  // Heads for operations that are not chosen cost nothing and cannot execute.
  assert.deepEqual(Object.keys(q).filter((k) => k.endsWith('_target')).sort(),
    ['click_target', 'select_target', 'type_text_target']);
  assert.deepEqual(Object.keys(q).filter((k) => k.startsWith('value_')).sort(), ['value_5', 'value_6']);
  assert.deepEqual(Object.keys(q.value_5.criteria).sort(), ['email', 'password', 'skip']);
});

test('scroll is only offered when the page actually reports one', () => {
  const flat = { ...OBS, actions: ACTIONS.filter((a) => a.kind !== 'scroll') };
  assert.ok(!ops(buildStepQuestions(flat, {})).includes('SCROLL_DOWN'));
});

test('validateAnswer accepts a consistent answer and rejects every inconsistent one', () => {
  const ids = ['a', 'b'];
  assert.ok(validateAnswer({ choice: 'a', confidence: 0.9, probabilities: { a: 0.8, b: 0.2 } }, ids));
  assert.ok(validateAnswer({ choice: 'a', confidence: 0.9 }, ids), 'probabilities are optional');
  assert.equal(validateAnswer({ choice: 'c', confidence: 0.9 }, ids), null, 'choice we never offered');
  assert.equal(validateAnswer({ choice: 'a', confidence: 0.9, probabilities: { a: 0.8, c: 0.2 } }, ids), null, 'distribution over other ids');
  assert.equal(validateAnswer({ choice: 'a', confidence: 0.9, probabilities: { a: 0.3, b: 0.2 } }, ids), null, 'does not sum to 1');
  assert.equal(validateAnswer({ choice: 'a', confidence: 0.9, probabilities: { a: 0.2, b: 0.8 } }, ids), null, 'peaks on the other one');
  assert.equal(validateAnswer({ choice: 'a', confidence: 4 }, ids), null, 'confidence out of range');
  assert.equal(validateAnswer(null, ids), null);
});

test('decide: the operation head picks which target head may execute', () => {
  const q = buildStepQuestions(OBS, DATA);
  const d = decideStep({ operation: { choice: 'CLICK', confidence: 0.9 }, click_target: { choice: '3', confidence: 0.9 },
    type_text_target: { choice: '5', confidence: 0.99 } }, q, DATA);
  assert.deepEqual([d.operation, d.target], ['CLICK', '3']);
  assert.deepEqual(d.fills, [], 'the unused type_text head does not type anything');
});

test('decide: TYPE_TEXT resolves the value head into the string to type', () => {
  const q = buildStepQuestions(OBS, DATA);
  const d = decideStep({ operation: { choice: 'TYPE_TEXT', confidence: 0.9 }, type_text_target: { choice: '5', confidence: 0.9 },
    value_5: { choice: 'email', confidence: 0.95 } }, q, DATA);
  assert.deepEqual(d.fills, [{ index: '5', key: 'email', text: 'a@b.co' }]);
});

test('decide: a low-confidence value is not typed', () => {
  const q = buildStepQuestions(OBS, DATA);
  const d = decideStep({ operation: { choice: 'TYPE_TEXT', confidence: 0.9 }, type_text_target: { choice: '5', confidence: 0.9 },
    value_5: { choice: 'email', confidence: 0.4 } }, q, DATA);
  assert.deepEqual(d.fills, []);
});

test('decide: DONE, BLOCKED, low confidence, and an invalid answer all fail closed', () => {
  const q = buildStepQuestions(OBS, DATA);
  assert.equal(decideStep({ operation: { choice: 'DONE', confidence: 0.9 } }, q, DATA).stop, 'done');
  assert.equal(decideStep({ operation: { choice: 'BLOCKED', confidence: 0.9 } }, q, DATA).stop, 'stuck');
  assert.equal(decideStep({ operation: { choice: 'CLICK', confidence: 0.3 } }, q, DATA).stop, 'stuck');
  assert.equal(decideStep(null, q, DATA).stop, 'stuck');
  // Operation says CLICK, target head names an element that head never offered.
  assert.equal(decideStep({ operation: { choice: 'CLICK', confidence: 0.9 }, click_target: { choice: '2', confidence: 0.9 } }, q, DATA).stop, 'stuck');
});

test('decide: WAIT and SCROLL need no target', () => {
  const q = buildStepQuestions(OBS, DATA);
  for (const choice of ['WAIT', 'SCROLL_DOWN']) {
    const d = decideStep({ operation: { choice, confidence: 0.9 } }, q, DATA);
    assert.deepEqual([d.operation, d.target, d.stop], [choice, null, null]);
  }
});

test('stuck: three executed actions in a row that changed nothing', () => {
  const nc = { operation: 'CLICK', changed: false };
  assert.equal(stuckFromHistory([nc, nc, nc]), true);
  assert.equal(stuckFromHistory([nc, nc]), false);
  assert.equal(stuckFromHistory([nc, { operation: 'CLICK', changed: true }, nc]), false);
  // Waiting is allowed to change nothing — that is what waiting is.
  assert.equal(stuckFromHistory([nc, { operation: 'WAIT', changed: false }, nc]), false);
});

test('step state gives Jev the element table, the viewport and the off-site links', () => {
  const s = buildStepState('log in', OBS, [], DATA);
  assert.ok(s.elements.includes('[1] link "Home"'));
  assert.ok(s.elements.some((e) => e.startsWith('[7] combobox "Country" · Morocco')));
  assert.deepEqual(s.external_links, ['Telegram -> https://t.me/x']);
  assert.match(s.viewport, /0–900 of 2400/);
});

test('step state names the fields that are still empty', () => {
  // Two regressions, one field. 2026-09-19 (speculative fills): without any mention of the fields Jev saw
  // an empty form and chose "Log in" at 0.45. 2026-09-21 (one operation per step): the old wording said the
  // fields "are filled just before this operation" — no longer true — and Jev submitted the empty fixture
  // form instead of typing. The list now means "still empty, fill these first".
  const s = buildStepState('log in', OBS, [], DATA);
  assert.deepEqual(s.fields_to_fill, ['Email', 'Password']);
  assert.equal(buildStepState('g', OBS, [], {}).fields_to_fill, undefined);
});

test('the rules Jev is given carry the lessons that were paid for', () => {
  const r = buildStepQuestions(OBS, DATA).operation.instructions;
  assert.match(r, /untrusted data/);
  assert.match(r, /autocomplete suggestion/);
  assert.match(r, /fields_to_fill/);
  assert.match(r, /viewport/);
  assert.match(r, /WAIT only when/);
});

test('personas replace data values and keep keys', () => {
  const d = personaData('invalid_input', DATA);
  assert.deepEqual(Object.keys(d).sort(), ['email', 'password']);
  assert.notEqual(d.email, 'a@b.co');
  assert.deepEqual(personaData('double_submit', { email: 'x' }), { email: 'x' });
  assert.ok(PERSONAS.length >= 4);
});

test('judge state keeps the URL but says SPAs may not change it', () => {
  // With the bare URL "/login.html", a visible dashboard was judged pass at 0.78; with the note, 0.98.
  const s = buildJudgeState('dashboard visible', '/login.html', 'snap');
  assert.equal(s.url, '/login.html');
  assert.match(s.url_note, /may not change/);
});

test('judge state carries native validation messages and the persona intent', () => {
  // type=email blocks submit with a native tooltip that is not in the DOM; without these the judge saw an
  // untouched form and returned pass at 0.10.
  const s = buildJudgeState('graceful', '/login.html', 'snap', { nativeValidation: ['Email: Please enter an email address.'], persona: 'invalid_input' });
  assert.deepEqual(s.native_validation, ['Email: Please enter an email address.']);
  assert.match(s.session, /invalid/);
  const plain = buildJudgeState('x', '/', 's', { nativeValidation: [], persona: 'normal' });
  assert.equal(plain.native_validation, undefined);
  assert.equal(plain.session, undefined);
});

test('compact snapshot drops url lines and keeps head and tail (footer) when long', () => {
  // mbardouni.dev: <main> alone was 20.5k chars; a 6k head cut hid the footer (contact) and the project grid.
  const snap = ['- banner:', '  - link "Home":', '    - /url: /ar', ...Array.from({ length: 2000 }, (_, i) => `  - paragraph: line ${i}`), '- contentinfo:', '  - link "Email me":', '    - /url: mailto:x@y.z'].join('\n');
  const c = compactSnapshot(snap, 4000);
  assert.ok(c.length <= 4100);
  assert.ok(!c.includes('/url:'));
  assert.ok(c.startsWith('- banner:'));
  assert.ok(c.includes('contentinfo') && c.includes('Email me'));
  assert.match(c, /trimmed/);
  assert.equal(compactSnapshot('- main:\n  - /url: /x\n  - heading "A"', 4000), '- main:\n  - heading "A"');
});

test('judge: page errors fail the flow even when Jev says pass', () => {
  assert.equal(judgeFlow({ verdict: { choice: 'pass', confidence: 0.99 } }, ['TypeError: x']).status, 'fail');
});

test('judge: pass, fail with cause, and fail-closed on missing or low confidence', () => {
  assert.equal(judgeFlow({ verdict: { choice: 'pass', confidence: 0.9 }, cause: { choice: 'none' } }, []).status, 'pass');
  const f = judgeFlow({ verdict: { choice: 'fail', confidence: 0.95 }, cause: { choice: 'backend_error', confidence: 0.9 } }, []);
  assert.deepEqual([f.status, f.cause], ['fail', 'backend_error']);
  assert.equal(judgeFlow(null, []).status, 'uncertain');
  assert.equal(judgeFlow({ verdict: { choice: 'pass', confidence: 0.5 } }, []).status, 'uncertain');
});

test('text helper: only {"text": "…"} is ever typed', () => {
  assert.equal(parseText({ text: 'Casablanca' }), 'Casablanca');
  assert.equal(parseText({ text: null }), null, 'the model said it has no value');
  assert.equal(parseText({ text: '' }), null);
  assert.equal(parseText({ text: 'x', note: 'here you go' }), null, 'chatty extra keys');
  assert.equal(parseText({ text: 'x'.repeat(2001) }), null);
  assert.equal(parseText('Casablanca'), null, 'bare prose is not a value');
  assert.equal(parseText(null), null);
});

test('text helper never writes into a secret field', async () => {
  assert.equal(await fieldText({ goal: 'log in' }, { secret: true }), null);
});

test('action space caps targets and keeps the option index stable', () => {
  const many = Array.from({ length: 200 }, (_, i) => ({ index: String(i + 1), kind: 'click', role: 'link', label: `L${i}`, external: false }));
  const { targets } = actionSpace(many, {});
  assert.equal(Object.keys(targets.CLICK).length, 80);
  const { targets: t2 } = actionSpace(ACTIONS, DATA);
  assert.equal(t2.SELECT['7:2'].value, 'fr');
});
