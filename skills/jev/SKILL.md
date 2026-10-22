---
name: jev
description: Use TypeSafe Jev (via OpenRouter) for fast, cheap, typed decisions instead of an LLM call — classify, route, gate, triage, score, pick a model tier. Triggers "/jev", "use jev", "classify these", "triage", "route this", "is this spam", "which model should do this", "gate before the LLM", "sentiment", "score each", and whenever code or a hook asks an LLM for a label, yes/no, score, or one-word answer, or Claude is about to read many items only to sort them. Also when adding AI decisions to Tokyo, godhome, mostqlAi, portfolio, Laravel apps, or dev-stack hooks. Also for e2e / browser tests and browsing agents — "e2e test", "playwright", "browser test", "did this step pass", "flaky test triage", "why did CI fail", driving a page with claude-in-chrome / agent-browser / Lightpanda — as the judge between the browser driver and any LLM; and for unit tests of code that calls Jev. Not for writing text, images, audio, or inputs over 32k tokens.
---

# Jev — typed decisions for software

Jev (TypeSafe "System One", OpenRouter `typesafe/jev-1.13`) takes **state + named questions** and returns
**typed answers with calibrated confidence**. ~0.5–1 s, ~$0.00002 per call ($0.042/M input, $0 output),
32k context, text only. It never writes prose — that is the point: no parsing, no hallucinated format.
(The API itself answers in ~100–300 ms; the 0.5–1 s is the CLI's Python start plus the round trip from here.)

## When Jev, when an LLM

| The output is… | Use |
|---|---|
| a label, yes/no, probability, score, routing target, model tier | **Jev** |
| an internal summary/digest of public data | free model (`deepseek/deepseek-v4-flash-0731:free`) |
| text a client/recruiter/public reads, or image understanding | Claude Sonnet 5 / Haiku 4.5 |
| computer use, browser/e2e testing, running tests, QA | Claude Haiku 5.5 for running and reading (`cliproxy/claude-haiku-5-5`, kind `test` T0-T2); Sonnet 5.5 for debugging and fixing (T3), then Opus 5.5 -> Gemini 4 Argon -> Grok 4.7 |
| Arabic text (translate, write, correct) | Claude Sonnet 5.5 (Haiku 5.5 for short text), Gemini 4 Argon fallback (`kinds.language`); no OpenAI (owner 2026-10-22) |
| code, debugging, multi-file work | Claude Sonnet 5.5 (frontend at xhigh); Opus 5.5 takes the task back when a worker fails |
| the hardest long-horizon work / GUI control | Claude Opus 5.5; long builds and parallel fan-out: Grok 4.7; >500k-context reads: Gemini 4 Argon |

Not sure? `jev route "<task>"` answers with the tier (`T0`–`T4`) and a model.

The pattern that saves the most: **Jev gates, the LLM writes.** Ask Jev first; only call the LLM when there
is something to write, and send low-confidence cases up a tier. Keep policy (thresholds, weights, rules) in code.

## System 1 and System 2

Jev is the **System 1**: the fast reflex. It is cheap enough to run on every item and every step, always on.
Claude (Opus / Fable) and GPT-6 Astra are the **System 2**: slow and deliberate. They set goals, write text and
code, handle the uncertain cases, and **retrain System 1**. Design every Jev integration as one of three
loops, and usually all three together:

| Loop | System 1 (Jev) | System 2 (LLM) | Escalation signal |
|---|---|---|---|
| **Screen** | judges every item: diff hunk, comment, log line, page, message | reads only the shortlist | risk / score above the bar, or confidence below it |
| **Act** | picks each next step from fresh observations: next click, next task, next skill | sets the goal and the bounded options, re-plans at milestones | `stuck`, `none_fit`, low confidence, a failure, a milestone |
| **Train** | logs every decision (`jev … --log TAG`) | reviews the log (`jev tune TAG`) and rewrites criteria, options, instructions and thresholds | disagreements, dismissed findings, clusters near the threshold |

Rules for splitting the work:

1. **System 1 owns anything frequent.** If a decision repeats, whether per item, per step or per prompt, and the
   answer is a label, yes/no, score or pick, it belongs to Jev. System 2 time is for what can't be decided
   that way.
2. **System 2 owns goals, prose, code, and the question design itself.** Jev never invents options, so a bad
   option list is a System 2 bug.
3. **The handoff up is small.** System 1 passes System 2 the state slice, the question, the answer and its
   confidence (why it escalated), not the raw pile. The handoff down is a goal, bounded options and thresholds.
4. **Move work down over time.** When System 2 keeps making the same call, turn that call into a Jev question
   with the System 2 examples as criteria. That is the "practice moves System 2 into System 1" step.
5. **Retrain by editing config, not by hoping.** Criteria, options and thresholds live in a question file or
   constants next to the code. `jev tune` output plus a System 2 pass changes that file, and the change gets a
   commit like any other code.
6. **Fail toward System 2.** A Jev error, timeout or low confidence escalates. It never silently passes.

Where the loops run in dev-stack:

| Part | Screen | Act | Train tag |
|---|---|---|---|
| Every prompt | `jev-skill-suggest` picks at most one relevant skill | Claude uses it or ignores it | `skill-suggest` |
| Orchestrator | Step 3b sizes each packet (trivial…hard) | spawns the right model | `orchestrator` |
| Code review | `jev-review diff` flags risky hunks | Opus 5.5 reviewer (xhigh) / Gemini 4 Argon second opinion / `/panel` read only those | `review` |
| Lint / scan | `jev-review lint`, `jev-review scan` | Haiku 5.5 (tests/QA) or Opus fix the shortlist | `lint`, `scan` |
| Browser / e2e | checkpoint verdict + cause | `jev-browse` picks each action; Haiku 5.5 runs the browser/e2e steps, Claude fixes failures | `browse` |
| Driving an agent (`drive-screen`) | `jev_gate.py` reads a herdr pane: prompt / working / idle / dialog / exited + in-project | `autodrive.py --herdr` approves safe prompts; anything else stops for a human | `drive-screen` |
| KB, hooks, project code | see [references/use-cases.md](references/use-cases.md) | | per call site |

## From a shell, hook, skill, pi, opencode, or Claude Code

`jev` is on PATH on the Mac (`~/.local/bin/jev` → `dev-stack/bin/jev`) and on MyContabo (`/usr/local/bin/jev`).

```bash
jev choice "Which team handles this" billing="charges, refunds" tech="bugs, outages" sales="pricing" -s "$MSG"
jev noul "The customer wants a refund" -s "$MSG" --yes 0.7 && escalate   # exit 0 = yes
jev score "How urgent" "can wait" "this week" "today" "right now" -s "$MSG" -q   # 0-based level
jev route "Summarize the HN front page" -q                                    # -> T1
echo '{"order":{"total":480,"items":3},"note":"arrived broken"}' | jev choice "Next step" refund=… replace=… ask_photo=… --min 0.8 -q || ask_llm
```
Exit codes: `--min` → 2 when confidence is below; `--yes` → 1 when below; 3 = API/key error. Always keep a
fallback path for exit ≠ 0. Run `jev --help` for everything.

### The jev-* tools (dev-stack `bin/`, all fail closed, all log for `jev tune`)

| Tool | What it screens | Use it when | Measured 2026-09-19 |
|---|---|---|---|
| `jev-skill-suggest "<prompt>"` | which one of ~170 installed skills fits (TypeSafe cookbook: 2-stage Choice + gate Nouls) | runs automatically in the UserPromptSubmit hook; `JEV_SKILL_SUGGEST=0` turns it off | 9/10 labelled prompts, no wrong picks, 0.5–1.1 s |
| `jev-review diff [BASE]` | every hunk: 5 risk Nouls + severity Score → `route: none/reviewer/codex/panel` | before any review (reviewer Pass 0, kb-dev Phase 9) | planted bugs → `panel`, clean diff → `none`, ~$0.00003/hunk |
| `jev-review lint [PATH…]` | secrets / PII in logs, names hiding side effects, useless or wrong comments; `.jev-lint.json` overrides | pre-commit / CI; exit 1 on error-level rules | caught the logged password as an error |
| `jev-review scan [DIR] [--run]` | code smells + garbage comments per 120-line window, cost estimate first | "find code smells", "clean up comments", codebase audits | dev-stack: 33 windows, $0.0015, 9 shortlisted |
| `jev-browse` | Jev picks one operation + its target per request (click/type/select/scroll/wait/done), then verdict + cause; `--flows`, `--adversarial N`, `--observe` to see what Jev is offered, `--autofill`, `--headful` to watch, `--screenshots DIR` for the visual (L3) check, `--login --profile NAME` once to test pages behind auth. Real Chrome by default; guards against invisible, covered and re-rendered elements | kb-dev Phase 8 for UI changes, `dogfood` first sweep | 3 flows right in ~3–5 s for $0.00025 |

### Claude Code itself

- **Bulk triage without flooding context:** loop `jev` over N items (issues, emails, jobs, log lines, KB files)
  and only read the ones that pass. Reading 300 items to sort them is the expensive way.
- **Pick the model/effort for a subtask** before spawning an agent: `jev route "<packet>" -q` → T0–T4.
  T0 means no agent at all — just call `jev`.
- Never send secrets. Client messages are fine for Jev (it's a decision, not training data on a free tier),
  but keep state to what the question needs.

## Designing questions (what makes Jev accurate)

1. **One narrow property per question.** Split "is this spam?" into `requests_credentials`,
   `unexpected_reward`, `sender_mismatch`… and combine in code.
2. **Pick the primitive by meaning:** one of a set → `choice`; whether it holds → `noul`; degree → `score`
   (levels are 0-based; 1.5 means between levels 1 and 2).
3. **Always offer an escape option** (`other`, `info`, `none`) — Jev cannot pick what you didn't offer.
4. **Contrastive criteria:** describe each option so it excludes its neighbours.
5. **Structured state beats a blob:** `{"latest_message":…, "recent_conversation":…, "sender":…}`.
   Mixed Arabic/Darija/French/English is fine.
6. **Thresholds scale with stakes:** auto-reply to a client ≥ 0.85; routing ≥ 0.75; skipping an LLM call
   only when the "nothing to do" answer is confident. Different states can't batch — fan out in parallel.
7. **Several questions about the same state go in one request** (the `raw` form / `askJev` map) — same latency.
   Speculative questions are fine too: ask the branch-specific ones up front and use only the relevant answers.
8. **Tell Jev what it can't see.** Things outside the state (a field about to be filled, a URL an SPA never
   changes, a native validation tooltip) swing confidence hard. Measured: 0.45 → 0.97 and 0.78 → 0.98 from
   one sentence of state or instruction. A/B the wording with `jev raw` before changing thresholds.

Limits: Choice ≤ 255 options; Score ≤ 11 levels (0–10); Noul has no `confidence`, and a Noul near 0.5 means
"undecided", not "medium"; state ≤ 32k tokens, text only. Choice/Score `confidence` is how concentrated the
distribution is. It is not permission to act; thresholds come from your own data. The official docs index
is `https://docs.typesafe.ai/llms.txt` (pages serve Markdown with `.md` appended). Read the closest cookbook
before designing a new integration.

## E2e tests, browsing, and code tests

Jev goes in the middle: the browser driver acts, Jev judges the page, an LLM runs only when Jev escalates.
Computer use, browser/e2e, running tests and QA run on Haiku 5.5 (`cliproxy/claude-haiku-5-5`, Haiku 4.5 as fallback); jdelegate routes them to kind `test`.
Ladder `L0` Playwright/agent-browser → `L1` Jev → `L2` cheap text LLM → `L3` vision → `L4` Opus/agent.

- Deterministic assertions first; Jev replaces fuzzy ones.
- One Jev call per checkpoint: `verdict` (pass/fail/uncertain) + `cause` (selector_drift, backend_error,
  auth, timeout, regression, none). Verified 5/5 correct, ~$0.000024, < 1 s.
- State = `{expected, url, page: <aria snapshot of one region, ≤ 8000 chars>}`. Never raw HTML or secrets.
- Fail closed: error / low confidence = `uncertain` → escalate, never `pass`. Cache answers by snapshot hash.
- Unit tests stub the Jev client and test the `null` fallback; one opt-in live contract test.
- Need a whole flow checked, not one page? `jev-browse --flows flows.json` runs the System 1 agent.
- Mobile app, or a suite mixing exact and agent steps? TesterArmy `e2e` (`npx e2e run`), see the mobile section of the reference.

Questions JSON, thresholds, Playwright/shell helpers, browsing-agent patterns, CI triage:
[references/e2e-browsing.md](references/e2e-browsing.md).

## In project code

Copy-paste clients (TypeScript, PHP/Laravel, Python) and the wire format are in
[references/clients.md](references/clients.md). Every client returns `null` on no key / error / low
confidence so the caller keeps its existing path. Key: `OPENROUTER_API_KEY`.

Where Jev fits in each of our projects (done and candidates): [references/use-cases.md](references/use-cases.md).

## Gotchas

- `/chat/completions` rejects Jev; the endpoint is `POST https://openrouter.ai/api/alpha/decisions`.
- It is not in `/api/v1/models`, so pi/opencode model pickers can't select it — call `jev` via bash instead.
- `noul` answers carry no `confidence` field; the probability is the signal.
- Python urllib needs a real `User-Agent` (Cloudflare 1010 otherwise); the CLI sets one.

## Local fallback: Laya

When Jev errors (out of quota, 402, no key, network), `bin/jev` asks the local `laya-serve`
daemon (127.0.0.1:8719, launchd `dev.mbardouni.laya-serve`, Mac only) before exiting 3. The answer
is tagged `"engine": "laya"` in the JSON output and the decision log, and stderr shows `jev: fallback=laya`.
Laya is 20-30× faster but weaker (A/B 2026-09-22: 73% vs 81% routing, mode collapse on many-option
choices, confidence 0.02-0.26), so:
- every `--min` gate fails closed (exit 2): routers go one tier up, which is the safe direction;
- `noul` probabilities bunch near 0.5, so `--yes 0.7` reads as no;
- `jev tune` and the capability-registry/outcomes readers skip Laya decisions;
- `jev-browse` / `jev-page` (Laya over-predicts pass) and `jev-review` (its risk nouls fall below 0.6,
  so every diff would route to "none") set `JEV_NO_LAYA=1`;
- importers calling `ask()` / `ask_many()` get Laya answers with no `--min`: their own thresholds
  decide (checked: jdelegate 0.4/0.6, jev-skill-suggest 0.6/0.8, retry-or-stop 0.85, all fail closed).
Daemon down or `JEV_NO_LAYA=1` → exit 3 as before. Env: `JEV_LAYA_URL`, `JEV_LAYA_TIMEOUT` (3 s).
Install: `ln -s ~/code/dev-stack/bin/laya-serve ~/.local/bin/`, copy `launchd/dev.mbardouni.laya-serve.plist`
to `~/Library/LaunchAgents/`, `launchctl bootstrap gui/$(id -u)` it. The port opens about 40 s after start.
