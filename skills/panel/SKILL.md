---
name: panel
description: Four-reviewer panel — Claude + Codex + Gemini + OpenCode/MiniMax plan/review the same target in parallel, then cross-review each other with confidence scores, then Claude synthesizes using weighted voting and explicit decision rationale. For load-bearing decisions where triangulation beats any single reviewer. Runs the KB-grounded chain once up front and saves the full transcript (3 rounds) into `ai-knowledge-base/raw/panel/` for `/kb-ingest`. Triggers "/panel", "panel plan", "panel review", "have the three review", "four-way review", "tribunal", "jury this", "triangulate", "all three review", or any plan/review Claude judges high-stakes enough to warrant it.
allowed-tools: Bash, Read, Write, Grep, Glob, Skill
---

# Panel (Claude + Codex + Gemini + OpenCode as peer advisors)

Four reviewers, three rounds, one weighted synthesis. Use when a single reviewer is not enough — architecture calls, pre-merge review on high-risk diffs, multi-module plans, anything the user flags as load-bearing.

## Role split (critical-task routing)

On critical tasks Claude's context is the scarce resource. Offload heavy thinking to the CLIs; keep Claude for synthesis + execution + user-facing decisions.

| Reviewer | Label | Strongest at | Use for |
|---|---|---|---|
| **Gemini** | C | plan + design | long-context plans, multi-module spec+code, design critique, UI/frontend, design-system drift |
| **Codex** (gpt-5.4) | B | plan + review | focused code review, bug hunt, security, narrow implementation plan |
| **OpenCode/MiniMax** | D | clarity + classification | UX copy clarity, issue severity labeling, summarization, cross-cutting concerns others miss |
| **Claude** | A | research + synthesis + execution | `/kb-query` + NotebookLM, reconciling CLI outputs, final weighted judgment, handing to specialist subagents |

Panel fires all four when the decision is critical enough that triangulation beats any single reviewer.

**Token-save rule (mandatory):** CLI outputs are persisted to `ai-knowledge-base/raw/` FIRST and Claude reads the artifact by file reference when synthesizing — never hold multi-page CLI responses in Claude's live context when a file path will do.

## The four steps

1. **Research (once)** — `/kb-query` + NotebookLM → single Prior-art block shared by all four.
2. **Round 1 — Independent drafts (parallel)** — Claude, Codex, Gemini, OpenCode each produce plan/review blind to the others.
3. **Round 2 — Cross-review with confidence scores (parallel)** — each reviewer critiques the other three and rates each P0 item (1–5 confidence).
4. **Round 3 — Weighted synthesis** — Claude builds the final artifact: confidence-weighted consensus + majority + preserved dissent + explicit decision rationale + unresolved conflicts for user tiebreak.

Then capture the full transcript to `ai-knowledge-base/raw/panel/<YYYY-MM-DD>-<slug>.md`.

## When to fire the panel

**Fire when:**
- Architectural decision with long-lived consequences (data model, auth, tenancy, billing).
- Pre-merge on a high-risk diff (migrations, cross-service contract changes, security-adjacent).
- Multi-module implementation plan where cross-cutting concerns dominate.
- User explicitly says "panel", "tribunal", "triangulate", "all three/four review".
- Claude genuinely disagrees with its own first pass and wants triangulation before committing.

**Do NOT fire for:**
- Trivial fixes / single-file edits.
- Tasks where speed matters more than certainty.
- Tasks `/kb-dev` or a single reviewer (`/codex`, `/gemini`) already covers cleanly.
- More than once per feature unless the scope genuinely changes — the panel is expensive.

Panel never auto-fires inside `/kb-dev`. User invocation or explicit Claude decision only, with a one-line "firing panel because X" preface so the cost is visible.

## Step 1 — Research (once, shared)

Run the KB chain **once**, not four times:

1. `/kb-query` with the target question → save `[[wikilinks]]` block.
2. If `Notebook ID` is configured in project `CLAUDE.md`, run `mcp__notebooklm-mcp__notebook_query` with the same question.
3. Collapse into a single **Prior art** preamble. All four reviewers get the same preamble — apples-to-apples.

## Step 2 & Step 3 — Deterministic Round 1 + Round 2 (`panel-run`)

Never pump six raw CLI transcripts through the live coordinator context. Write the shared **Prior art** block and your own blind **Plan A (Claude)** draft to temp files first (before seeing any peer output), then invoke `panel-run` **once**:

```bash
scratch_dir="$(mktemp -d)"
cat > "$scratch_dir/prior-art.md" <<'EOF'
<kb-query citations + NotebookLM excerpt>
EOF

cat > "$scratch_dir/draft-a.md" <<'EOF'
<Claude's independent Round 1 plan/review — written blind before running peers>
EOF

panel-run \
  --target "<file / module / feature / PR>" \
  --scope "<plan | review | bug-hunt | security | design-review>" \
  --slug "<kebab-slug>" \
  --prior-art-file "$scratch_dir/prior-art.md" \
  --draft-a-file "$scratch_dir/draft-a.md" \
  --prompt-extra "ONLY <boundary>. Do NOT <out-of-scope>." \
  --include-dir "<relevant path>"
```

What `panel-run` does deterministically in a single call:
1. **Round 1 (parallel, blind):** Runs Reviewer B (`codex exec --model gpt-5.4 --sandbox read-only`), Reviewer C (`gemini --approval-mode plan`), and Reviewer D (`opencode run -m opencode/minimax-m2.5-free`) concurrently, saving verbatim drafts to `ai-knowledge-base/raw/panel/<YYYY-MM-DD>-<slug>/r1-*.md`.
2. **Automatic retries & fallbacks:** Retries any failed/timed-out CLI once with a narrower prompt, drops unavailable CLIs cleanly (`4-reviewer` -> `3-reviewer` -> `2-reviewer`), and exits `2` if all external CLIs are unavailable.
3. **Round 2 (parallel, confidence-scored 1–5):** Feeds each external reviewer the peer drafts (`B` gets `A+C+D`, `C` gets `A+B+D`, `D` gets `A+B+C`), saves `r2-*.md` + `digest.json`, pre-populates `ai-knowledge-base/raw/panel/<YYYY-MM-DD>-<slug>.md`, and prints **only** file paths + parsed `TOP_CRITIQUES` sorted by confidence (`1–5`).

**Confidence scale (used in Round 2 & Round 3):**
```
5 — Certain. I would stake the decision on this.
4 — High confidence. Strong evidence or reasoning.
3 — Moderate. Plausible but I could be wrong.
2 — Low. Gut feeling or thin evidence.
1 — Speculative. Surfacing anyway because the risk is non-trivial.
```

After `panel-run` finishes:
1. Read `r1-B-codex.md`, `r1-C-gemini.md`, `r1-D-opencode.md` (and `r2-*.md` when `TOP_CRITIQUES` needs context) by file reference.
2. Formulate **Claude's Round 2 critique on B + C + D** (`<reviewer>:<item>` — confidence `1–5` — issue — recommendation) and proceed directly to Step 4.

## Step 4 — Round 3: Weighted synthesis (Claude)

Claude writes the final artifact using **confidence-weighted voting**.

### Weighting formula

For each item, compute its **signal weight**:
```
signal = sum of confidence scores from reviewers who raised this item
```

- Same item raised by all 4 at confidence 5 → signal = 20 (act immediately)
- Item raised by 1 reviewer at confidence 2 → signal = 2 (surface, don't block)
- Use signal to rank items within each section

### Tie-breaking rules (when 2/2 split)

1. **Fail-safe default:** prefer the more conservative option (less irreversible, smaller blast radius).
2. **Domain weight:** on security/correctness items, Codex signal gets ×1.5 multiplier; on design/UX items, Gemini and OpenCode signals get ×1.5 multiplier.
3. **If tie persists after domain weighting** → surface to user as "USER DECIDES".

### Output structure

```markdown
# Panel verdict — <target>

## Decision rationale
<2–3 sentences: why this panel was called, what the key fork was, what principle broke the tie>

## Consensus (all four agree — act on these)
- <item> [signal: N] — raised by A/B/C/D, confidence avg X.X — <what to do>
- ...

## Majority (3-of-4 — strong signal, one dissent preserved)
- <item> [signal: N] — raised by <three>, <fourth> dissented (conf N) because <reason>. Adopt. **Flag if <trigger condition>.**
- ...

## Weighted minority (2-of-4 — moderate signal, surface for awareness)
- <item> [signal: N] — raised by <two> (conf avg X.X). Not blocking. Revisit if <trigger>.
- ...

## Preserved dissent (1-of-4, low signal but non-trivial risk)
- <item> from <reviewer> (conf N) — not adopted. Worth revisiting if <specific trigger>.
- ...

## Unresolved conflicts — USER DECIDES
- <conflict> — A says X (conf N), B says Y (conf N), C says Z (conf N), D says W (conf N). Signals: X=N, Y=N. Recommended default: <fail-safe option>.
- ...

## Final plan / review
<agreed artifact, ranked by signal weight, ready to hand to writing-plans or to act on>
```

Rules:
- Never silently drop a minority view. If all four disagree, surface all four.
- If panel splits 2/2, apply tie-breaking rules above; if still unresolved, USER DECIDES.
- Consensus ≠ correct. Flag consensus items that rest on a shared assumption the user may want to challenge.
- Lead with decision rationale — the user needs to understand WHY before they can tiebreak.

## Step 5 — Capture

Write the full transcript to:

```
ai-knowledge-base/raw/panel/<YYYY-MM-DD>-<slug>.md
```

Template:
```markdown
---
source: panel
reviewers: [claude, codex, gemini, opencode]
codex_model: gpt-5.4
gemini_model: <model used>
opencode_model: minimax-m2.5-free
date: <YYYY-MM-DD>
target: <file / module / feature / PR>
scope: <plan | review | bug-hunt | security | design-review>
---

## Prior art consulted
- /kb-query: <one-line summary + [[wikilinks]]>
- NotebookLM: <one-line summary, or "n/a">

## Round 1 — Independent drafts
### Plan A (Claude)
<verbatim>

### Plan B (Codex)
<verbatim>

### Plan C (Gemini)
<verbatim>

### Plan D (OpenCode/MiniMax)
<verbatim>

## Round 2 — Cross-review (with confidence scores)
### Claude on B + C + D
<verbatim>

### Codex on A + C + D
<verbatim>

### Gemini on A + B + D
<verbatim>

### OpenCode on A + B + C
<verbatim>

## Round 3 — Weighted synthesis
<final artifact from Step 4>
```

Tell user: "Panel saved to `<path>`. Run `/kb-ingest` to promote to research."

## Fallbacks

- **Codex unavailable** → run panel with Claude + Gemini + OpenCode, label as 3-reviewer panel, note missing voice.
- **Gemini unavailable** → same, with Codex + OpenCode.
- **OpenCode unavailable** → run panel with Claude + Codex + Gemini (original 3-reviewer mode), note D is absent.
- **Both CLIs (Codex + Gemini) unavailable** → run Claude + OpenCode only, label as 2-reviewer panel, warn user that signal weight is low.
- **All CLIs unavailable** → abort panel, tell user, fall back to Claude alone.
- **One reviewer times out mid-round** → retry once with narrower scope. If still failing, drop that reviewer, adjust signal-weight denominators accordingly, continue.

## Guardrails

- Only fire on explicit invocation or on Claude's explicit "this is load-bearing, firing panel because X" — never silently.
- Research step runs ONCE; all four share the preamble. No parallel `/kb-query` storms.
- None of the reviewers write code. Claude / specialist subagents execute the agreed plan.
- YOLO mode: auto-accept all items with signal ≥ 16 (consensus, high confidence) without user ping. Surface anything below that threshold and all USER DECIDES items.
- Save the transcript before acting on the synthesis — the KB entry is the durable artifact.
- OpenCode/MiniMax is fast but not deep on architecture. Its signal on UX/clarity items carries ×1.5 domain weight; its signal on correctness/security carries ×0.8 weight in the formula.

## Invocation

```
/panel plan the multi-tenant migration
/panel review this PR for the billing service
/panel design-review the new dashboard against DESIGN.md
/panel yolo   # auto-accept high-signal consensus, only ping user on conflicts
```
