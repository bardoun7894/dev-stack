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

Real Chrome is the default: it lays pages out, so visibility, viewport, occlusion and scrolling are real
checks rather than assumptions, and L3 screenshots come from the same run. Lightpanda stays an option for
very wide parallel L0/L1 sweeps where none of those guards matter (`--cdp http://127.0.0.1:9222`).

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
above in a loop, and the flow ends with the verdict + cause checkpoint. Only failures reach Claude.

```bash
jev-browse --url http://127.0.0.1:3000/login --goal "sign in" --expect "dashboard shows today's sales" \
  --data '{"email":"qa@example.com","password":"…"}'
jev-browse --flows e2e/flows.json --json          # [{name,url,goal,expect,data}], all in parallel
jev-browse --url … --goal … --data … --adversarial 5   # personas: normal, invalid_input, hostile_input,
                                                        # double_submit, back_button — reports what breaks
jev-browse --url … --goal … --observe             # print the page exactly as Jev is offered it, decide nothing
jev-browse --url … --goal … --autofill            # let a small LLM write values --data does not cover
```

### One Chrome, two drivers (jev-browse + chrome-devtools-mcp)

Both speak CDP, so they share a browser instead of competing for one. Jev runs the flows in it; Claude
attaches to the *same tabs* through `chrome-devtools-mcp` to read console, network and performance when
something goes red. One browser, one profile, one set of logins.

```bash
jev-chrome                                                   # start it (visible), prints http://127.0.0.1:9333
jev-browse --login --profile shared --url https://app/login  # sign in once, by hand
jev-browse --cdp http://127.0.0.1:9333 --flows e2e/flows.json
```

Registered globally as the `chrome-devtools` MCP server:
`npx -y chrome-devtools-mcp@latest --browserUrl http://127.0.0.1:9333`. It only connects while
`jev-chrome` is up; start the browser first, or the server reports as failed.

Port **9333**, not 9222 — 9222 is Lightpanda, and pointing either tool at the wrong browser is a confusing
failure rather than a loud one.

Two things this fixed, both found by trying it:

- **`claude-in-chrome` cannot carry a page state.** Its JS-eval result is truncated around 1 000 characters
  and a 4 KB string comes back as `[BLOCKED: Base64 encoded data]`. A real app's action table is 5–15 KB,
  so the extension can never hand one to Jev. `chrome-devtools-mcp` has no such cap because it is a CDP
  server, not an extension channel. The extension stays useful for *looking* at a page, not for feeding one
  to a decision model.
- **`--cdp` used to open a logged-out context.** Playwright's `newContext()` on a CDP-attached Chrome
  returns an empty one, so a shared, signed-in browser silently stopped being signed in. It now opens a tab
  in the browser's existing context and only falls back to `newContext()` for Lightpanda, which exposes none.

### The replay cache — pay once per UI change, not per run

`--cache` records what a **passing** flow did into `.jev-browse/<flow>-<persona>.json` and replays it at L0
next time. Measured on the fixture login (4 steps), 2026-09-21:

| | Jev calls | wall clock |
|---|---|---|
| cold (records) | 6 | 6.8 s |
| warm (replays) | **1** | **1.3 s** |
| warm, after the submit button was renamed | 3 | 3.1 s |

Steps are recorded **by meaning** — operation + role + accessible name (+ href, + option value) — never by
element index, which shifts the moment anything above it renders. A recorded step that no longer matches
abandons the replay *from that point*: Jev takes over for the rest of the flow and the recording is
rewritten. So renaming a button costs one step's worth of decisions, not a red suite.

Two properties that keep this honest, both verified:

- **The judge is never cached.** It is the assertion. With the flow fully replayed (`jev=1`), breaking the
  app still returned `fail / auth` — a cached run that cannot go red is a suite that has stopped testing.
- **A failing run never records.** After that failure the previous good recording was still on disk.

`--re-record` forces a fresh recording; `--cache-dir DIR` moves the store. Commit the store to get the
L0 replay in CI, or leave it ignored to have CI always pay full price.

### Testing pages behind a login

`--profile NAME` runs in a persistent Chrome profile of its own under `~/.cache/jev-browse/profiles/`.
Sign in **once, by hand**, and every later run with that profile carries the session:

```bash
jev-browse --login --profile tokyo --url https://dash.example/login   # you log in; close the window to save
jev-browse --profile tokyo --flows e2e/dashboard.json                 # already signed in, no credentials anywhere
```

No credential passes through the agent, Jev or any model — `--login` just hands you the keyboard. It is
never your everyday profile: Chrome 136+ refuses remote debugging on the default user-data-dir, and a test
run has no business acting inside a live browsing session.

Verified 2026-09-21 with a negative control: run 2 on the signed-in profile passed in **0 steps** (nothing
to do, already authenticated) while the same check on a fresh profile returned `fail / auth`.

Flows sharing a profile share one browser context (that is what carries the cookies) and run as parallel
tabs; without `--profile` each flow gets an isolated context instead.

### One request per step, two decisions (speculative fan-out)

Ported from [browser-use/jev-ultrafast](https://github.com/browser-use/jev-ultrafast) on 2026-09-21. Each
step sends **one** Jev request carrying the operation question *and* one target head per operation:

```text
operation        CLICK | TYPE_TEXT | SELECT | SCROLL_DOWN | SCROLL_UP | WAIT | DONE | BLOCKED
click_target     [1] link "About" · [6] button "Sign in"
type_text_target [3] textbox "Email" · [4] textbox "Password"
select_target    [5:1] Country → Morocco · [5:2] Country → France
value_3          email | password | skip        ← only when --data is given
```

The operation answer decides which head may execute; every other head is discarded unexecuted, so
"which operation" and "which element" cost one round trip. Each head contains only compatible elements,
and `SELECT` enumerates the observed options, so a dropdown value is *picked*, never written.

### What the agent will not do

- **Act on an inconsistent answer.** `validateAnswer` requires the choice to be one we offered, the
  distribution to cover exactly those ids, sum to 1 and peak on the chosen one. Anything else is `null`.
- **Click something it cannot see.** Elements hidden by `aria-hidden`, `inert`, `hidden`, zero size, CSS
  or opacity are never offered — the `.reveal`/opacity class of false positive.
- **Click through an overlay.** Immediately before input the target is re-resolved and hit-tested
  (`e.contains(document.elementFromPoint(x,y))`); a covered control is rejected and the page re-observed.
- **Click the wrong element after a re-render.** Node identity is a `WeakMap` on the page, so an id
  survives a React re-render and a vanished or renamed node is *detected* rather than re-matched by index.
  Nothing is written to the DOM under test (the old `data-jev` attribute is gone).
- **Turn model output into code.** A choice is only ever an index into a table this process built; it never
  becomes a selector, a coordinate, a shell command or JavaScript.
- **Leak a password.** Password fields are filled from `--data` but their value never reaches Jev or the
  text helper — the state and the run log carry `••• (n)`.

### Cost of the port

Measured on the local fixture (`--chrome`, real Chrome), 2026-09-21: a 4-step login (type email → type
password → select country → submit) runs in ~5 s and passes; the same fixture with a 1-second overlay stops
at `stale` instead of clicking through it; a below-the-fold goal that the old agent could not reach at all
now finishes in 2 `SCROLL_DOWN`s.

**Seeing the UI.** Jev reads text, never pixels. `--headful` opens a real Chrome window (one flow at a time,
slowed down, a red outline on each element before it is clicked) so a person can watch. `--screenshots DIR`
(implies `--chrome`, headless Chrome) saves `NN.png` per step plus `final.png` / `final-full.png` per flow;
layout, styling, overflow and mixed-language checks are then a vision model (Claude reading the PNGs), the L3
rung. First run on mbardouni.dev caught what the text never showed: an Arabic post listed in the English blog
index and a truncated title.

**Read-only by default.** Without `--data` or `--allow-submit` it never presses a button inside a form, and it
never follows a link off the site under test; off-site links (Telegram, WhatsApp, app stores) are passed to
Jev as `external_links` so "find how to join" can finish as `done`. Learned on the live mbardouni.dev: a
"find how to hire" flow pressed the real contact form's Send (the backend rejected the empty POST).

Exit 0 all pass, 1 any fail/uncertain, 3 no browser / no Jev. **Runs real Chrome by default** — every
geometric guard above needs a browser that lays the page out. `--cdp URL` drives an already-running browser
instead; one that reports no layout (Lightpanda does not) degrades to DOM-only visibility with no scrolling
and no occlusion check, which is weaker, not equivalent. Adversarial input only against apps you own.

Lessons baked into it (all from the decision log, `jev tune browse`):
- **No layout means no guards.** Lightpanda parses but never lays out: rects are 0×0, `elementFromPoint` and
  `checkVisibility` are missing. The snapshot detects this (`hasLayout: false`) and drives the DOM directly
  (native value setter + `input`/`change`, `element.click()`). It also allows one browser context per CDP
  connection, so give each parallel session its own connection.
- **`fields_to_fill` means "still empty", not "about to be filled".** Under the old speculative-fill loop the
  wording "filled just before this operation" took a ready form from 0.45 → 0.97. Once each step became one
  operation that sentence was false, and Jev submitted an empty fixture form instead of typing into it.
- **Only offer a target you can execute.** TYPE_TEXT was offered on already-filled fields while `--data`
  supplies values for empty ones only; Jev picked one, nothing could execute, and the flow ended at
  `no_value` — non-deterministically, depending on which field it picked.
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
