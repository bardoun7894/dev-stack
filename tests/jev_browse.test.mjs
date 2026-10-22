// node --test tests/  — policy of the Jev browser agent (no browser, no network)
import test from 'node:test';
import assert from 'node:assert/strict';
import { clickTarget, elementLabel, isSensitiveField, compactSnapshot, buildStepQuestions, buildStepState, buildJudgeState, decideStep, personaData, judgeFlow, PERSONAS } from '../skills/jev/scripts/browse-core.mjs';

const ELEMENTS = [
  { id: 0, kind: 'link', label: 'Home', href: '/index.html' },
  { id: 1, kind: 'button', label: 'Log in' },
  { id: 2, kind: 'input', label: 'Email', type: 'email', empty: true },
  { id: 3, kind: 'input', label: 'Password', type: 'password', empty: true },
  { id: 4, kind: 'input', label: 'Search', type: 'text', empty: false },
];

test('step questions: one action choice plus a fill choice per empty input when data is given', () => {
  const q = buildStepQuestions(ELEMENTS, { email: 'a@b.co', password: 'pw' });
  assert.deepEqual(Object.keys(q.action.criteria).sort(), ['click_0', 'click_1', 'done', 'stuck']);
  assert.deepEqual(Object.keys(q).filter((k) => k.startsWith('fill_')).sort(), ['fill_2', 'fill_3']);
  assert.deepEqual(Object.keys(q.fill_2.criteria).sort(), ['email', 'password', 'skip']);
});

test('step questions: no fill questions without data', () => {
  const q = buildStepQuestions(ELEMENTS, {});
  assert.equal(Object.keys(q).filter((k) => k.startsWith('fill_')).length, 0);
});

test('decide: confident click plus fills', () => {
  const d = decideStep({
    action: { choice: 'click_1', confidence: 0.9 },
    fill_2: { choice: 'email', confidence: 0.95 },
    fill_3: { choice: 'skip', confidence: 0.9 },
  });
  assert.deepEqual(d, { fills: [{ id: 2, key: 'email' }], click: 1, stop: null });
});

test('decide: low confidence stops as stuck, done stops as done', () => {
  assert.equal(decideStep({ action: { choice: 'click_1', confidence: 0.3 } }).stop, 'stuck');
  assert.equal(decideStep({ action: { choice: 'done', confidence: 0.9 } }).stop, 'done');
  assert.equal(decideStep({ action: { choice: 'stuck', confidence: 0.9 } }).stop, 'stuck');
});

test('decide: low-confidence fill is not applied', () => {
  const d = decideStep({ action: { choice: 'click_1', confidence: 0.9 }, fill_2: { choice: 'email', confidence: 0.4 } });
  assert.deepEqual(d.fills, []);
});

test('personas replace data values and keep keys', () => {
  const d = personaData('invalid_input', { email: 'a@b.co', password: 'pw' });
  assert.deepEqual(Object.keys(d).sort(), ['email', 'password']);
  assert.notEqual(d.email, 'a@b.co');
  assert.deepEqual(personaData('double_submit', { email: 'x' }), { email: 'x' });
  assert.ok(PERSONAS.length >= 4);
});

test('step state tells Jev which fields will be filled before the click', () => {
  // Without this, Jev saw an empty form and chose "Log in" at only 0.45 (log, 2026-09-19).
  const s = buildStepState('log in', '/login.html', 'snap', [], ELEMENTS, { email: 'a@b.co' });
  assert.deepEqual(s.fields_to_fill, ['Email', 'Password']);
  assert.equal(buildStepState('g', '/', 's', [], ELEMENTS, {}).fields_to_fill, undefined);
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

test('read-only by default: no form submits without data, never off-site links', () => {
  // mbardouni.dev 2026-09-19: a "find how to hire" flow clicked the live contact form's Send button (the
  // backend rejected the empty POST), and the community flow crashed on tg:// and wandered to t.me.
  const els = [
    { id: 0, kind: 'link', label: 'About', href: '/en/about', external: false },
    { id: 1, kind: 'link', label: 'Telegram', href: 'https://t.me/x', external: true },
    { id: 2, kind: 'button', label: 'Send message', inForm: true },
    { id: 3, kind: 'button', label: 'Menu', inForm: false },
  ];
  const keys = (q) => Object.keys(q.action.criteria).sort();
  // Since f808c7b no button at all is offered without data/--allow-submit: a button outside a <form> can
  // still POST via fetch, so read-only mode only follows on-site links.
  assert.deepEqual(keys(buildStepQuestions(els, {})), ['click_0', 'done', 'stuck']);
  assert.deepEqual(keys(buildStepQuestions(els, { email: 'a@b.co' })), ['click_0', 'click_2', 'click_3', 'done', 'stuck']);
  assert.deepEqual(keys(buildStepQuestions(els, {}, { allowSubmit: true })), ['click_0', 'click_2', 'click_3', 'done', 'stuck']);
  const s = buildStepState('join', '/en/community', 'snap', [], els, {});
  assert.deepEqual(s.external_links, ['Telegram -> https://t.me/x']);
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

test('label: a typed value never becomes the label, least of all a password', () => {
  assert.equal(elementLabel({ type: 'password', value: 'hunter2', name: 'pw' }), 'pw');
  assert.equal(elementLabel({ type: 'text', value: 'me@example.com', name: 'email' }), 'email');
  assert.equal(elementLabel({ type: 'text', autocomplete: 'cc-number', value: '4111111111111111' }), '');
  assert.equal(elementLabel({ type: 'submit', value: 'Log in' }), 'Log in');
  assert.equal(elementLabel({ type: 'submit', value: 'x', name: 'otp_submit' }), 'otp_submit');
  assert.equal(elementLabel({ type: 'text', ariaLabel: '  Search   site ', value: 'q' }), 'Search site');
});

test('sensitive fields: password type, sensitive autocomplete, sensitive names', () => {
  assert.ok(isSensitiveField({ type: 'password' }));
  assert.ok(isSensitiveField({ type: 'text', autocomplete: 'one-time-code' }));
  assert.ok(isSensitiveField({ type: 'text', autocomplete: 'section-a new-password' }));
  assert.ok(isSensitiveField({ type: 'tel', name: 'cvv' }));
  assert.ok(!isSensitiveField({ type: 'email', name: 'email', autocomplete: 'email' }));
});

test('Jev unavailable: a null answer is jev_unavailable, never stuck or a page verdict', () => {
  assert.deepEqual(decideStep(null), { fills: [], click: null, stop: 'jev_unavailable' });
  assert.deepEqual(judgeFlow(null, []), { status: 'uncertain', cause: 'jev_unavailable' });
  assert.deepEqual(judgeFlow({ verdict: { choice: 'pass', confidence: 0.4 } }, []), { status: 'uncertain', cause: 'unknown' });
});

test('click guard: only ids that were offered as click options can be clicked', () => {
  const els = [
    { id: 0, kind: 'link', label: 'About', href: '/about', external: false },
    { id: 1, kind: 'link', label: 'Out', href: 'https://evil.example', external: true },
    { id: 2, kind: 'button', label: 'Send', inForm: true },
    { id: 3, kind: 'input', label: 'Email', empty: true },
  ];
  assert.equal(clickTarget(els, {}, 0)?.id, 0);
  assert.equal(clickTarget(els, {}, 1), null);
  assert.equal(clickTarget(els, {}, 2), null);
  assert.equal(clickTarget(els, {}, 3), null);
  assert.equal(clickTarget(els, {}, 99), null);
  assert.equal(clickTarget(els, {}, NaN), null);
  assert.equal(clickTarget(els, { email: 'a@b.co' }, 2)?.id, 2);
  assert.equal(clickTarget(els, {}, 2, { allowSubmit: true })?.id, 2);
});
