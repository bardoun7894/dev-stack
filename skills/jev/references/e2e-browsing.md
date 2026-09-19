# Jev in e2e tests, browser automation, and code tests

Jev sits **in the middle**: the browser driver (Playwright, agent-browser, claude-in-chrome, Lightpanda) acts,
Jev judges what the page shows, and another LLM runs only when Jev says so or is not confident.

Measured 2026-09-19 on five checkpoint pages (success, 500 banner, wrong cart total, bounced to login,
still loading): all five verdicts and causes correct, confidence 0.84–1.0, ~$0.000024 and 0.7–0.9 s per call
with both questions in one request.

## The ladder

Named `L0`–`L4` so it doesn't clash with `jev route`'s `T0`–`T4` model tiers.

| Rung | Who | Handles | Cost |
|---|---|---|---|
| L0 | Playwright / agent-browser, deterministic | navigation, clicks, known selectors, exact text, status codes, URLs | free, ms |
| L1 | **Jev** | "did this step work?", why it failed, what rung goes next, which link/action to take | ~$0.00002, < 1 s |
| L2 | cheap text LLM (Haiku 4.5; free `opencode/ling-3.0-flash-fin-free` with Haiku fallback) | repair a broken selector from the trimmed aria tree, extract a region | cheap |
| L3 | vision model on a screenshot | layout, visual regressions, canvas/charts, anything Jev said `uncertain` about | medium |
| L4 | Opus / `dogfood` / `codex-computer` | exploratory runs, failures L1–L3 couldn't explain | expensive, on demand |

Rules of the ladder:

1. **Deterministic first.** If `expect(page).toHaveURL(...)` or an exact text match answers it, don't call Jev.
   Jev replaces *fuzzy* assertions (the ones people write as brittle regexes or skip entirely), not exact ones.
2. **Every checkpoint is one Jev request** with all its questions (verdict + cause, optionally next action).
3. **Policy lives in code.** Thresholds decide the rung; Jev only answers.
4. **Fail closed.** Jev error, timeout, missing key, or low confidence = `uncertain` → escalate. Never `pass`.
5. **Pay once per UI change, not per run.** Anything L2+ learns (a repaired selector, a recorded flow) is cached
   and replayed at L0 next time.

## Checkpoint questions (verified)

```json
{
  "verdict": {"type": "choice", "instructions": "Does the page show the expected outcome of the test step?",
    "criteria": {
      "pass": "the expected outcome is visible on the page",
      "fail": "an error, wrong data, or a different page is visible",
      "uncertain": "the page text is not enough to tell (still loading, empty, ambiguous)"}},
  "cause": {"type": "choice", "instructions": "If the step did not pass, the most likely cause",
    "criteria": {
      "selector_drift": "the page is fine but the element the test needs was renamed or moved",
      "backend_error": "a server error, 500, or failed request message is shown",
      "auth": "logged out, login page, forbidden or 401/403",
      "timeout": "spinner, skeleton, or loading text still showing",
      "regression": "the feature itself behaves wrong (wrong total, missing item, wrong state)",
      "none": "the step passed"}}
}
```

State shape — structured, small, one region:

```json
{"expected": "cart shows 2 items, total 480 DH",
 "url": "/cart",
 "page": "<aria snapshot of the region under test, ≤ 8000 chars>",
 "console_errors": ["…last 5…"],
 "failed_requests": ["POST /api/cart 500"]}
```

`expected` is the test's intent in plain words. That sentence is the whole assertion, so write it the way
you'd explain the step to a tester: concrete values, not "it works".

## Policy (defaults, tune per suite)

| Jev says | Do |
|---|---|
| `pass` ≥ 0.85 | next L0 step |
| `fail` ≥ 0.8 and cause `regression` / `backend_error` / `auth` ≥ 0.8 | report red with the cause, no LLM |
| cause `selector_drift` | L2 repairs the selector from the aria tree → re-run the step → cache the new selector |
| cause `timeout` | wait for network idle once, re-checkpoint; if it repeats, report a flake to root-cause (no retry loops) |
| `uncertain`, or anything below its bar | L3 screenshot check |
| L3 still unsure | L4, and mark the step for a human |
| Jev null / exit 3 | same as `uncertain` |

## Getting the page state (keep it small)

Never send raw HTML, full-page dumps, cookies, tokens, or screenshots. Scope to the region the step touches.

| Driver | State for Jev |
|---|---|
| Playwright (TS/Python, ≥ 1.49) | `await page.locator("main").ariaSnapshot()` (or the form/card/dialog under test) |
| agent-browser (`dogfood`) | `agent-browser --session S snapshot` (content) — not `-i`, that's for refs |
| claude-in-chrome | `get_page_text` or `read_page` on the tab, then pipe the relevant part to `jev` via Bash |
| Lightpanda (CDP `127.0.0.1:9222`) | Playwright `chromium.connectOverCDP("http://127.0.0.1:9222")`, then `ariaSnapshot()` as above |

Lightpanda for L0/L1 speed and parallel runs; real Chromium only for L3 (it renders, Lightpanda doesn't paint).

## Playwright helper (TypeScript)

Reuses the `askJev` client from [clients.md](clients.md).

```ts
import { createHash } from "node:crypto";
import type { Page } from "@playwright/test";
import { askJev } from "./jev";

type Next = "continue" | "report" | "heal" | "wait" | "look";
const QUESTIONS = { /* verdict + cause from "Checkpoint questions" above */ };
const cache = new Map<string, { next: Next; cause: string }>();

export async function checkpoint(page: Page, expected: string, region = "main") {
  const snap = (await page.locator(region).ariaSnapshot()).slice(0, 8000);
  const key = createHash("sha1").update(expected + "\n" + snap).digest("hex");
  const hit = cache.get(key);
  if (hit) return hit;

  const a = await askJev({ expected, url: new URL(page.url()).pathname, page: snap }, QUESTIONS, 3000)
    .catch(() => null);                                   // fail closed
  const d = decide(a);
  if (a) cache.set(key, d);                               // never cache an error
  return d;
}

function decide(a: any): { next: Next; cause: string } {
  const v = a?.verdict, c = a?.cause;
  if (!v) return { next: "look", cause: "jev_unavailable" };
  if (v.choice === "pass" && v.confidence >= 0.85) return { next: "continue", cause: "none" };
  if (v.choice === "fail" && v.confidence >= 0.8 && c?.confidence >= 0.8) {
    if (c.choice === "selector_drift") return { next: "heal", cause: c.choice };
    if (c.choice === "timeout") return { next: "wait", cause: c.choice };
    if (c.choice !== "none") return { next: "report", cause: c.choice };
  }
  return { next: "look", cause: c?.choice ?? "unknown" };
}
```

In the test: `const d = await checkpoint(page, "order placed, confirmation shows an order number");`
then `expect(d.next, d.cause).toBe("continue")` after handling `heal` / `wait` / `look` in a fixture.
Persist `cache` to disk (e.g. `.e2e-cache/jev.json`) between runs if the suite is large.

## From a shell (agent-browser, claude-in-chrome, CI steps)

```bash
snap=$(agent-browser --session shop snapshot | head -c 8000)
jq -n --arg e "order placed, confirmation shows an order number" --arg p "$snap" \
  --argjson q "$(cat e2e/jev-checkpoint.json)" '{state:{expected:$e,page:$p},questions:$q}' \
  | jev raw | jq -r '.answers.verdict.choice, .answers.cause.choice'
# exit 3 → treat as uncertain
```

Quick one-offs: `jev noul "The page shows an error or a broken state" -s "$snap" --yes 0.7 && take_screenshot`.

## jev-browse: the System 1 browser agent (ready-made)

`bin/jev-browse` (source `skills/jev/scripts/jev-browse.mjs`, policy in `browse-core.mjs`) does all of the
above in a loop: each step is one Jev request (an action Choice over links and buttons plus a fill Choice per
empty field), and the flow ends with the verdict + cause checkpoint. Only failures reach Claude.

```bash
jev-browse --url http://127.0.0.1:3000/login --goal "sign in" --expect "dashboard shows today's sales" \
  --data '{"email":"qa@example.com","password":"…"}'
jev-browse --flows e2e/flows.json --json          # [{name,url,goal,expect,data}], all in parallel
jev-browse --url … --goal … --data … --adversarial 5   # personas: normal, invalid_input, hostile_input,
                                                        # double_submit, back_button — reports what breaks
```

**Read-only by default.** Without `--data` or `--allow-submit` it never presses a button inside a form, and it
never follows a link off the site under test; off-site links (Telegram, WhatsApp, app stores) are passed to
Jev as `external_links` so "find how to join" can finish as `done`. Learned on the live mbardouni.dev: a
"find how to hire" flow pressed the real contact form's Send (the backend rejected the empty POST).

Exit 0 all pass, 1 any fail/uncertain, 3 no browser / no Jev. Defaults to Lightpanda at `127.0.0.1:9222`
(Mac launchd, MyContabo systemd); `--cdp` for another Chromium. Adversarial input only against apps you own.

Lessons baked into it (all from the decision log, `jev tune browse`):
- **Lightpanda has no layout**, so Playwright's `fill`/`click` visibility checks never pass. Drive the DOM
  (native value setter + `input`/`change` events, `element.click()`, `goto` for links). It also allows one
  browser context per CDP connection, so give each parallel session its own connection.
- **Tell Jev the fields get filled first** (`fields_to_fill` + "ready to submit"): 0.45 → 0.97 on a ready form.
- **SPAs keep the URL.** A visible dashboard under `/login.html` scored `pass` 0.78; adding a note that the
  URL may not change → 0.98. The same applies to the Playwright helper above.
- **Native validation is invisible in the DOM** (`type=email`, `required` show a tooltip). Pass
  `validationMessage`s in the judge state, or bad-input sessions look like nothing happened.
- Hostile input echoed back into a textbox still reads as alarming and comes back `uncertain`. That's
  intended, and it escalates to L3 (screenshot) rather than passing.

## Browsing agents (Claude driving a browser to get something done)

- **Next action:** state = trimmed interactive snapshot + goal; `choice` over the candidate links/buttons
  (+ `none_fit`). Verified picking the right tweet at 0.99. Below 0.8 → Claude reads the page itself.
- **"Am I there yet?":** `noul "This page contains <what the goal needs>"` before reading the page in full.
- **Many results / rows / links:** loop `jev` over each item and only open the ones that pass. Reading 50 search
  results to find 3 relevant ones is the expensive way.
- **Blockers:** one `choice` for `captcha | login_wall | paywall | cookie_banner | none` before acting.
  Captcha/login → stop and ask the user; never try to beat them.

## Failure triage in CI

On a red run, send `{test, step, error, console_tail, failed_requests}` with the `cause` question alone.
Group failures by cause in the summary. Only `regression` pages anyone; `selector_drift` opens a heal job;
`backend_error` / `auth` point at the environment, not the test.

## Code tests (unit / integration) that touch Jev

- **Never call Jev from unit tests.** Stub the client (`askJev`, `App\Services\Jev`, `ask_jev`) — network and a
  model in a unit test make it slow and non-deterministic.
- **Test both paths:** a confident answer, and `null` (no key / error / low confidence) falling back to the
  existing path. The fallback is the part that breaks in production.
- **One opt-in live contract test** (tagged, skipped without `OPENROUTER_API_KEY`) that sends 3–5 known states
  and checks the answers, so a Jev model bump that changes behaviour shows up. Pin `JEV_MODEL` in CI.
- Test the **policy function** (`decide`) as a pure unit: it is where the real logic lives.

## Anti-patterns

- Jev as the only assertion when an exact check exists (L0 first).
- Whole-page or raw HTML state → slower, less accurate, and 32k cap.
- One wide question ("is this page correct?"). Split into narrow ones with an escape option.
- Treating a Jev error or timeout as `pass`.
- Retrying a test until Jev says `pass`. That's a flake with extra steps.
- Sending secrets: strip auth tokens, cookies, emails of real users, and payment fields from the snapshot.
- Screenshots or visual questions to Jev — it's text only. That's L3.
