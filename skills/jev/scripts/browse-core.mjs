// Pure policy for the Jev browser agent (System 1 acts, thresholds live here). Tested in tests/jev_browse.test.mjs.

export const ACTION_MIN = 0.5;
export const FILL_MIN = 0.6;
export const VERDICT_MIN = 0.8;
const MAX_CLICK_OPTIONS = 80;
const MAX_FILL_FIELDS = 8;

export const CHECKPOINT = {
  verdict: {
    type: 'choice', instructions: 'Does the page show the expected outcome of the test step?',
    criteria: {
      pass: 'the expected outcome is visible on the page',
      fail: 'an error, wrong data, or a different page is visible',
      uncertain: 'the page text is not enough to tell (still loading, empty, ambiguous)',
    },
  },
  cause: {
    type: 'choice', instructions: 'If the step did not pass, the most likely cause',
    criteria: {
      selector_drift: 'the page is fine but the element the test needs was renamed or moved',
      backend_error: 'a server error, 500, or failed request message is shown',
      auth: 'logged out, login page, forbidden or 401/403',
      timeout: 'spinner, skeleton, or loading text still showing',
      regression: 'the feature itself behaves wrong (wrong total, missing item, wrong state)',
      none: 'the step passed',
    },
  },
};

export const HEALTH = {
  verdict: {
    type: 'choice', instructions: 'Did the app handle this user session gracefully?',
    criteria: {
      pass: 'a normal page, a clear validation or error message for bad input, or the task succeeded',
      fail: 'a server error, stack trace, blank or garbled page, script error, stuck loading, or wrong data shown',
      uncertain: 'cannot tell from the page text',
    },
  },
  cause: CHECKPOINT.cause,
};

// Fields whose typed value must never reach Jev (or a label): passwords, OTPs, card data.
const SENSITIVE_AUTOCOMPLETE = /\b(current-password|new-password|one-time-code|cc-[a-z-]+|transaction-amount)\b/i;
const SENSITIVE_NAME = /pass|pwd|secret|token|otp|cvv|cvc|card.?num|ssn|iban|pin\b/i;
const BUTTON_TYPES = ['submit', 'button', 'reset', 'image'];

export function isSensitiveField(raw) {
  return raw.type === 'password' || SENSITIVE_AUTOCOMPLETE.test(raw.autocomplete || '')
    || SENSITIVE_NAME.test(`${raw.name || ''} ${raw.idAttr || ''}`);
}

// Label shown to Jev for one element. `value` is only a label for button-like inputs (their caption), never
// for a field the user or a fill typed into, and never for a sensitive field.
export function elementLabel(raw) {
  const value = BUTTON_TYPES.includes(raw.type) && !isSensitiveField(raw) ? raw.value : '';
  return (raw.ariaLabel || raw.forText || raw.wrapText || raw.placeholder || raw.innerText || value || raw.name
    || raw.href || '').trim().replace(/\s+/g, ' ').slice(0, 60);
}

export const PERSONAS = ['normal', 'invalid_input', 'hostile_input', 'double_submit', 'back_button'];

export function personaData(persona, data) {
  const out = {};
  for (const k of Object.keys(data || {})) {
    if (persona === 'invalid_input') out[k] = k.toLowerCase().includes('mail') ? 'not-an-email' : '';
    else if (persona === 'hostile_input') out[k] = `<script>alert(1)</script>${'x'.repeat(300)} ' "; --`;
    else out[k] = data[k];
  }
  return out;
}

// Read-only by default: without test data (or --allow-submit) the agent never submits a form, and it never
// leaves the site under test (off-site links are reported in the state instead of clicked).
export function clickable(elements, data, { allowSubmit = false } = {}) {
  const canSubmit = allowSubmit || Object.keys(data || {}).length > 0;
  return elements.filter((x) => (x.kind === 'link' && !x.external) || (x.kind === 'button' && canSubmit));
}

export function buildStepQuestions(elements, data, opts = {}) {
  const criteria = {};
  for (const e of clickable(elements, data, opts).slice(0, MAX_CLICK_OPTIONS)) {
    criteria[`click_${e.id}`] = `${e.kind} "${e.label}"${e.href ? ` -> ${e.href}` : ''}`;
  }
  criteria.done = 'the goal is already achieved on the current page (including when what it asks for is one of '
    + 'the `external_links`); nothing more to do';
  criteria.stuck = 'none of these moves toward the goal, or the goal is impossible from here';
  const q = {
    action: {
      type: 'choice',
      // A/B 2026-09-19: the old "Fields … are filled before the click" wording left a ready login form at
      // 0.40–0.49 (click vs stuck); saying the form is ready to submit gave 0.97–0.98.
      instructions: 'Which single click moves `goal` forward from the current page? The fields in `fields_to_fill` '
        + 'are filled with the right values just before this click, so a form that only needs those fields is ready to submit.',
      criteria,
    },
  };
  const keys = Object.keys(data || {});
  if (keys.length) {
    for (const e of elements.filter((x) => x.kind === 'input' && x.empty).slice(0, MAX_FILL_FIELDS)) {
      const c = Object.fromEntries(keys.map((k) => [k, `the value for "${k}"`]));
      c.skip = 'none of these values belongs in this field, or it should stay empty for this goal';
      q[`fill_${e.id}`] = { type: 'choice', instructions: `Which value belongs in the form field "${e.label}" (type ${e.type})?`, criteria: c };
    }
  }
  return q;
}

// Whole-page aria snapshot, compacted: link targets are already in the element list, and a long page keeps
// its start (banner, nav, first content) and end (footer: contact, social links) instead of a head-only cut.
export function compactSnapshot(snap, max = 12000) {
  const s = snap.split('\n').filter((l) => !/^\s*- \/url:/.test(l)).join('\n');
  if (s.length <= max) return s;
  const tail = Math.floor(max * 0.25);
  const marker = '\n  … (middle of the page trimmed) …\n';
  return s.slice(0, max - tail - marker.length) + marker + s.slice(-tail);
}

export function buildStepState(goal, url, page, history, elements, data) {
  const s = { goal, url, page, history: history.slice(-5), data_keys: Object.keys(data || {}) };
  const ext = elements.filter((e) => e.kind === 'link' && e.external).slice(0, 20);
  if (ext.length) s.external_links = ext.map((e) => `${e.label} -> ${e.href}`);
  if (s.data_keys.length) {
    const empty = elements.filter((e) => e.kind === 'input' && e.empty).slice(0, MAX_FILL_FIELDS);
    if (empty.length) s.fields_to_fill = empty.map((e) => e.label);
  }
  return s;
}

const PERSONA_NOTES = {
  invalid_input: 'this session deliberately submitted invalid values (bad email, empty fields); rejecting them with a validation message is the correct, graceful outcome',
  hostile_input: 'this session deliberately submitted hostile values (script tags, very long strings, quotes); rejecting or safely displaying them is graceful, executing or crashing on them is not',
  double_submit: 'this session clicked the submit button twice quickly',
  back_button: 'this session pressed the browser back button after the first action',
};

export function buildJudgeState(expected, url, page, { nativeValidation = [], persona = 'normal' } = {}) {
  const s = { expected, url, url_note: 'single-page apps may not change the URL after actions; judge by the page content', page };
  if (nativeValidation.length) s.native_validation = nativeValidation;
  if (PERSONA_NOTES[persona]) s.session = PERSONA_NOTES[persona];
  return s;
}

export function decideStep(answers) {
  // No answer at all (no key, network, bad JSON) is Jev being unavailable, not the page being a dead end.
  if (answers == null) return { fills: [], click: null, stop: 'jev_unavailable' };
  const fills = [];
  for (const [k, a] of Object.entries(answers || {})) {
    if (k.startsWith('fill_') && a.choice !== 'skip' && (a.confidence ?? 0) >= FILL_MIN) {
      fills.push({ id: Number(k.slice(5)), key: a.choice });
    }
  }
  const a = answers?.action;
  if (!a || (a.confidence ?? 0) < ACTION_MIN || a.choice === 'stuck') return { fills, click: null, stop: 'stuck' };
  if (a.choice === 'done') return { fills, click: null, stop: 'done' };
  return { fills, click: Number(String(a.choice).replace('click_', '')), stop: null };
}

export function judgeFlow(answers, pageErrors) {
  if (pageErrors && pageErrors.length) return { status: 'fail', cause: 'page_error', detail: pageErrors.slice(0, 3) };
  const v = answers?.verdict;
  if (answers == null) return { status: 'uncertain', cause: 'jev_unavailable' };
  if (!v || (v.confidence ?? 0) < VERDICT_MIN) return { status: 'uncertain', cause: answers.cause?.choice ?? 'unknown' };
  if (v.choice === 'pass') return { status: 'pass', cause: 'none' };
  if (v.choice === 'fail') return { status: 'fail', cause: answers.cause?.choice ?? 'unknown' };
  return { status: 'uncertain', cause: answers.cause?.choice ?? 'unknown' };
}
