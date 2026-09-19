---
name: jev
description: Use TypeSafe Jev (via OpenRouter) for fast, cheap, typed decisions instead of an LLM call — classify, route, gate, triage, score, pick a model tier. Triggers "/jev", "use jev", "classify these", "triage", "route this", "is this spam", "which model should do this", "gate before the LLM", "sentiment", "score each", and whenever code or a hook asks an LLM for a label, yes/no, score, or one-word answer, or Claude is about to read many items only to sort them. Also when adding AI decisions to Tokyo, godhome, mostqlAi, portfolio, Laravel apps, or dev-stack hooks. Also for e2e / browser tests and browsing agents — "e2e test", "playwright", "browser test", "did this step pass", "flaky test triage", "why did CI fail", driving a page with claude-in-chrome / agent-browser / Lightpanda — as the judge between the browser driver and any LLM; and for unit tests of code that calls Jev. Not for writing text, images, audio, or inputs over 32k tokens.
---

# Jev — typed decisions for software

Jev (TypeSafe "System One", OpenRouter `typesafe/jev-1.13`) takes **state + named questions** and returns
**typed answers with calibrated confidence**. ~0.5–1 s, ~$0.00002 per call ($0.042/M input, $0 output),
32k context, text only. It never writes prose — that is the point: no parsing, no hallucinated format.

## When Jev, when an LLM

| The output is… | Use |
|---|---|
| a label, yes/no, probability, score, routing target, model tier | **Jev** |
| an internal summary/digest of public data | free model (`deepseek/deepseek-v4-flash-0731:free`) |
| text a client/recruiter/public reads, or image understanding | Claude Sonnet 5 / Haiku 4.5 |
| code, debugging, multi-file work | Claude Opus 5 |
| the hardest long-horizon work / GUI control | Fable 5.1 / GPT-6 Astra |

Not sure? `jev route "<task>"` answers with the tier (`T0`–`T4`) and a model.

The pattern that saves the most: **Jev gates, the LLM writes.** Ask Jev first; only call the LLM when there
is something to write, and send low-confidence cases up a tier. Keep policy (thresholds, weights, rules) in code.

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

## E2e tests, browsing, and code tests

Jev goes in the middle: the browser driver acts, Jev judges the page, an LLM runs only when Jev escalates.
Ladder `L0` Playwright/agent-browser → `L1` Jev → `L2` cheap text LLM → `L3` vision → `L4` Opus/agent.

- Deterministic assertions first; Jev replaces fuzzy ones.
- One Jev call per checkpoint: `verdict` (pass/fail/uncertain) + `cause` (selector_drift, backend_error,
  auth, timeout, regression, none). Verified 5/5 correct, ~$0.000024, < 1 s.
- State = `{expected, url, page: <aria snapshot of one region, ≤ 8000 chars>}`. Never raw HTML or secrets.
- Fail closed: error / low confidence = `uncertain` → escalate, never `pass`. Cache answers by snapshot hash.
- Unit tests stub the Jev client and test the `null` fallback; one opt-in live contract test.

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
