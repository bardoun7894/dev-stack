---
name: codex
description: OpenAI Codex CLI as a sharp-eyed second-opinion REVIEWER and PLANNER. ALWAYS runs the KB-grounded chain — /kb-query (+ NotebookLM when a notebook_id is configured) first, then `codex exec` (review OR plan), then persist output into the KB `raw/` inbox so /kb-ingest can promote it to research. Triggers "/codex", "use codex", "run codex", "have codex review", "codex second opinion", "codex bug hunt", "codex plan", "have codex draft a plan", "codex help me plan". Also fires when Claude judges Codex's meticulous analysis would complement its own plan or review.
allowed-tools: Bash, Read, Write, Grep, Glob, Skill
---

# Codex (KB-grounded reviewer + planner)

Codex wears two hats on this stack:

1. **Reviewer** — sharp-eyed second opinion on code / diffs / PRs.
2. **Planner** — detailed, edge-case-aware implementation plans that Claude then executes.

Either way it never runs blind — it is always sandwiched between a KB research step and a KB capture step so its output compounds into the knowledge base instead of evaporating into the transcript.

## Codex as planner (how it helps Claude plan)

Inside `/kb-dev`, the planning phase is normally Claude + `writing-plans`. Escalate to Codex when:

- The feature spans multiple modules and Claude wants an independent decomposition.
- Edge cases matter more than speed (migrations, auth, billing, state machines).
- Claude already drafted a plan and wants it stress-tested before committing.
- The user says "have codex plan", "codex draft", "get a second plan from codex".

**Plan-mode handoff:**

1. Research step (Step 1 below) — same as review.
2. Run `codex exec` with the **Implementation Planning** prompt template.
3. Capture Codex's plan into `raw/codex/` (Step 3).
4. Claude reads the Codex plan, reconciles it with its own draft (or `plan.md` if spec-kit), surfaces deltas to the user, then the agreed plan goes to `writing-plans` → `tasks.md` → execution.

Codex proposes. Claude + user decide. Codex never writes code on this stack — edits stay with Claude, the orchestrator, and its specialist subagents.

## The standing chain — do NOT skip steps

Every Codex invocation (review OR plan) runs this chain in order:

1. **Research (KB + NotebookLM)** — gather prior art before Codex looks at the code / feature.
2. **Analyze (codex exec)** — run Codex with the research injected into the prompt. Mode = review | bug-hunt | plan | security.
3. **Capture (raw → KB)** — write Codex's output into `ai-knowledge-base/raw/codex/<YYYY-MM-DD>-<slug>.md` so `/kb-ingest` can promote it.

Skipping step 1 wastes Codex tokens re-deriving known context. Skipping step 3 means the next session loses the findings. Both are forbidden.

### Step 1 — Research first (always)

Before `codex exec`:

1. Invoke `/kb-query` with the review target as the question (e.g. "What do we already know about the auth middleware / prior bugs / decisions?"). Save the cited `[[wikilinks]]` block — it becomes Codex's context.
2. If the project `CLAUDE.md` defines a NotebookLM `Notebook ID`, run `mcp__notebooklm-mcp__notebook_query` with the same question and save the response.
3. Collapse both into a single **Prior art** preamble. Pass it into Codex's prompt so the review starts from known ground.

If `/kb-query` returns "no results", say so explicitly in the Prior art block — don't fabricate context.

### Step 1b — KB awareness + off-host data (SSH)

Before running Codex:

1. **KB paths always in scope.** Point Codex at `~/ai-knowledge-base/` alongside cwd so it can read KB articles directly if the Prior-art block is too narrow. Include it via the workspace:
   ```bash
   cd "$PROJECT_ROOT" && \
     CODEX_WORKSPACE="$PROJECT_ROOT:$HOME/ai-knowledge-base" codex exec ...
   ```
   (or pass both paths via whatever workspace flag the installed codex version supports — read `codex exec --help`.)
2. **Off-host data via SSH — Claude stages, Codex reads.** If the target file / log / dump lives on a remote host (Contabo, Hostinger, any `~/.ssh/config` host) and not in the current folder, Claude runs the `ssh` / `scp` / `rsync` fetch FIRST, drops the data into a temp dir inside the workspace, then invokes Codex against the local copy. Keep Codex in `--sandbox read-only`; Claude owns the network.
   ```bash
   STAGE=$(mktemp -d) && \
     rsync -a user@host:/path/to/remote/data "$STAGE/" && \
     codex exec --sandbox read-only "<prompt referencing $STAGE>" 2>&1
   ```
3. **If Codex reports "I need data from X" mid-review,** stop, let Claude fetch via SSH, stage into the workspace, re-run Codex with the expanded prompt. Never hand Codex raw network credentials.

### Step 2 — Run Codex with grounded prompt

Non-interactive pattern (inline prompt, not piped stdin):

```bash
codex exec \
  --model gpt-5.4 \
  --sandbox read-only \
  "<grounded prompt (includes KB paths + any staged off-host data)>" \
  2>&1
```

Grounded prompt template:

```
Prior art from our KB (trust this — don't re-derive):
<kb-query citations + NotebookLM excerpt>

Target: <file(s) / module / diff>
Task: <review | bug-hunt | plan | security>
Scope: ONLY <boundary>. Do NOT <out-of-scope>.
Format: `file:line` - severity - issue - suggested fix
Skip preambles. Lead with findings.
```

Defaults: `gpt-5.4`, `read-only` sandbox. Only escalate to `workspace-write` if the task explicitly requires file generation (rare — Claude does the edits, Codex reviews).

### Step 3 — Capture findings into the KB

After Codex returns, write the findings to:

```
ai-knowledge-base/raw/codex/<YYYY-MM-DD>-<slug>.md
```

Template:

```markdown
---
source: codex
model: gpt-5.4
date: <YYYY-MM-DD>
target: <file / module / PR>
scope: <review | bug-hunt | plan | security>
---

## Prior art consulted
- /kb-query: <one-line summary + [[wikilinks]]>
- NotebookLM: <one-line summary, or "n/a">

## Codex findings
<verbatim codex output, trimmed of preambles>

## Claude synthesis
<1–3 bullets — which findings are load-bearing, which are noise, what to action>
```

Then tell the user: "Findings saved to `<path>`. Run `/kb-ingest` to promote to research, or `/kb-compile` at end of day."

If `ai-knowledge-base/raw/` does not exist, run `/kb-setup` first (standing bootstrap rule).

## When to use Codex

**Fire Codex when:**
- Deep code review for security, correctness, or subtle bugs
- Second-opinion review on critical code paths before merge
- Detailed implementation planning with edge-case focus
- Claude is about to declare "looks good" on something non-trivial — let Codex poke holes

**Do NOT fire Codex for:**
- Simple / obvious fixes Claude handles alone
- Interactive debugging (Codex exec is one-shot)
- Speed-over-depth tasks
- Trivial refactors

## Invocation methods

### Method 1 — Explicit `/codex`

```
/codex review the authentication middleware for security issues
/codex --model gpt-5.4 analyze this algorithm
/codex --sandbox workspace-write generate tests for this module
```

| Flag | Values | Default |
|---|---|---|
| `--model` | any model name | gpt-5.4 |
| `--sandbox` | read-only, workspace-write, danger-full-access | read-only |

### Method 2 — Claude auto-spawns

When Claude judges Codex would add value (major PR review, pre-merge sanity check, security-adjacent diff), spawn the `codex-agent` subagent with the grounded prompt from Step 2. Synthesize Codex's findings with Claude's own analysis, then persist via Step 3.

## Prompting patterns (task-specific)

All prompts end with: `Skip preambles. Lead with findings.`

**Security review**
```
Review <target> for security vulnerabilities.
Focus ONLY on: auth, injection, data exposure, access control, SSRF, deserialization.
Do NOT suggest style or refactor changes.
Format: `file:line` - severity (P0/P1/P2) - issue
```

**Bug hunt**
```
Find bugs in <target>.
Look for: edge cases, off-by-one, null handling, race conditions, unhandled errors.
ONLY report actual bugs — not style.
Format: `file:line` - bug - suggested fix
```

**Code review**
```
Review <target> for correctness and reliability.
Focus ONLY on: logic errors, missing error handling, incorrect assumptions.
Ignore: style, naming, formatting.
Format: `file:line` - issue - recommendation
```

**Implementation plan**
```
Create implementation plan for: <feature>.
Constraints: <existing patterns / Prior art from KB>.
Output:
1. Overview
2. Files to modify (with line ranges)
3. Implementation steps
4. Edge cases
No code samples unless critical.
```

## Error handling

**Codex not installed** →
```
Codex CLI is not installed.
  brew install codex
  codex login
Docs: https://developers.openai.com/codex/cli
```

**Auth errors** → `codex login`.
**Timeout** → narrow scope, re-run.
**Sandbox error on write** → re-run with `--sandbox workspace-write` only if write is truly required.

## Guardrails

- Never run Codex without Step 1 research — the value of the second opinion depends on not re-deriving context Claude already has.
- Never skip Step 3 capture — orphan findings are a KB leak.
- Default `read-only` sandbox. Prefer Claude for edits, Codex for review.
- `gpt-5.4` unless the user overrides with `--model`.
- Output format: always `file:line` references so findings are navigable.
