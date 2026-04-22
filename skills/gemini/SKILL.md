---
name: gemini
description: Google Gemini CLI as a long-context + DESIGN-oriented second-opinion REVIEWER and PLANNER. Strongest on design critique (visual polish, design-system adherence, UI/UX review of screenshots + code together), whole-repo sweeps, multi-module plans, and spec+code joint review. ALWAYS runs the KB-grounded chain — /kb-query (+ NotebookLM when a notebook_id is configured) first, then `gemini -p` in plan/read-only mode, then persist output into the KB `raw/` inbox so /kb-ingest can promote it to research. Triggers "/gemini", "use gemini", "run gemini", "have gemini review", "gemini design review", "gemini UI critique", "gemini second opinion", "gemini bug hunt", "gemini plan", "have gemini draft a plan", "gemini help me plan". Also fires when Claude judges Gemini's long-context, multimodal, or design-eye strengths would complement its own plan or review.
allowed-tools: Bash, Read, Write, Grep, Glob, Skill
---

# Gemini (KB-grounded reviewer + planner)

Gemini wears three hats on this stack, mirroring the `codex` skill and extending it:

1. **Reviewer** — long-context second opinion on code / diffs / PRs / whole-repo sweeps.
2. **Planner** — multi-module implementation plans that Claude then executes.
3. **Design critic** — Gemini's strong suit. Feed it screenshots + the relevant component code + the project's `DESIGN.md` (or Tailwind config / tokens file) and it will critique visual hierarchy, spacing, typography, token adherence, design-system drift, and polish gaps that purely code-reading reviewers miss.

Either way it never runs blind — it is always sandwiched between a KB research step and a KB capture step so its output compounds into the knowledge base instead of evaporating into the transcript.

## When to pick Gemini vs Codex

| Use Gemini when… | Use Codex when… |
|---|---|
| **Design review** — UI/UX, visual polish, design-system drift, token adherence, screenshots vs `DESIGN.md` | Pure code review / logic bugs |
| Long context matters (whole-repo sweep, large diff, many files) | Sharp, focused review of a specific file / module |
| Cross-file or cross-doc reasoning (spec + code together) | Tight bug-hunt / security pass on a narrow target |
| Multimodal inputs (screenshots, PDFs of design docs, Figma exports) | Pure code analysis |
| Planning a feature that touches many subsystems or has heavy UI | Planning a feature scoped to one backend area |

Running BOTH in parallel is allowed when the user wants maximum triangulation on a critical decision — but default to one or the other to keep token cost sane.

## Gemini as planner (how it helps Claude plan)

Inside `/kb-dev`, the planning phase is normally Claude + `writing-plans`. Escalate to Gemini when:

- The feature touches many modules and long context is load-bearing.
- A spec / doc / diagram needs to be read alongside the code in one shot.
- Claude already drafted a plan and wants an independent long-context critique.
- The user says "have gemini plan", "gemini draft", "get a second plan from gemini".

**Plan-mode handoff:**

1. Research step (Step 1 below) — same as review.
2. Run `gemini -p` with `--approval-mode plan` and the **Implementation Planning** prompt template.
3. Capture Gemini's plan into `raw/gemini/` (Step 3).
4. Claude reads the Gemini plan, reconciles it with its own draft (or `plan.md` if spec-kit), surfaces deltas to the user, then the agreed plan goes to `writing-plans` → `tasks.md` → execution.

Gemini proposes. Claude + user decide. Gemini never writes code on this stack — edits stay with Claude, the orchestrator, and its specialist subagents.

## The standing chain — do NOT skip steps

Every Gemini invocation (review OR plan) runs this chain in order:

1. **Research (KB + NotebookLM)** — gather prior art before Gemini looks at the code / feature.
2. **Analyze (`gemini -p`)** — run Gemini with the research injected into the prompt. Mode = review | bug-hunt | plan | security.
3. **Capture (raw → KB)** — write Gemini's output into `ai-knowledge-base/raw/gemini/<YYYY-MM-DD>-<slug>.md` so `/kb-ingest` can promote it.

Skipping step 1 wastes Gemini tokens re-deriving known context. Skipping step 3 means the next session loses the findings. Both are forbidden.

### Step 1 — Research first (always)

Before `gemini -p`:

1. Invoke `/kb-query` with the target as the question (e.g. "What do we already know about the auth middleware / this feature area / prior bugs / decisions?"). Save the cited `[[wikilinks]]` block — it becomes Gemini's context.
2. If the project `CLAUDE.md` defines a NotebookLM `Notebook ID`, run `mcp__notebooklm-mcp__notebook_query` with the same question and save the response.
3. Collapse both into a single **Prior art** preamble. Pass it into Gemini's prompt so the analysis starts from known ground.

If `/kb-query` returns "no results", say so explicitly in the Prior art block — don't fabricate context.

### Step 1b — KB awareness + off-host data (SSH)

Before running Gemini:

1. **KB paths always in scope.** Add `~/ai-knowledge-base` to `--include-directories` so Gemini can read KB articles (`knowledge/`, `raw/`, `daily/`) directly when the Prior-art block is not exhaustive:
   ```bash
   gemini -p "<prompt>" \
     --approval-mode plan \
     --include-directories "$PROJECT_ROOT,$HOME/ai-knowledge-base" \
     -o text 2>&1
   ```
2. **Off-host data via SSH — Claude stages, Gemini reads.** If the target file / log / dump lives on a remote host (any `~/.ssh/config` host — Contabo, Hostinger, etc.) and not in the current folder, Claude runs the `ssh` / `scp` / `rsync` fetch FIRST, stages the data into a temp dir, then points Gemini's `--include-directories` at it. Keep `--approval-mode plan`; Claude owns the network.
   ```bash
   STAGE=$(mktemp -d) && \
     rsync -a user@host:/path/to/remote/data "$STAGE/" && \
     gemini -p "<prompt referencing $STAGE>" \
       --approval-mode plan \
       --include-directories "$PROJECT_ROOT,$HOME/ai-knowledge-base,$STAGE" \
       -o text 2>&1
   ```
3. **If Gemini reports "I need data from X" mid-review,** stop, let Claude fetch via SSH, re-run Gemini with the staged dir added to `--include-directories`. Never hand Gemini raw network credentials — it stays in plan/read-only mode.

### Step 2 — Run Gemini with grounded prompt

Non-interactive pattern (prompt passed via `-p`, include-dirs to widen context):

```bash
gemini \
  -p "<grounded prompt (includes KB paths + any staged off-host data)>" \
  --approval-mode plan \
  -o text \
  --include-directories "<cwd>,<KB path>,<any staged off-host dir>" \
  2>&1
```

Key flags:
- `-p, --prompt` — non-interactive (headless) prompt
- `-m, --model` — override model (default: whatever `gemini` picks; 2.5-pro-class recommended for code)
- `--approval-mode plan` — read-only; Gemini cannot mutate files. Use this for all review and plan modes on this stack.
- `--include-directories` — widen workspace to cross-file / whole-repo contexts (Gemini's strength)
- `-o text` — plain text output (switch to `json` if you need to parse)
- `-y / --yolo` — FORBIDDEN on this stack. Never auto-approve Gemini mutations; Claude owns edits.

Grounded prompt template:

```
Prior art from our KB (trust this — don't re-derive):
<kb-query citations + NotebookLM excerpt>

Target: <file(s) / module / diff / feature area>
Task: <review | bug-hunt | plan | security>
Scope: ONLY <boundary>. Do NOT <out-of-scope>.
Format: `file:line` - severity - issue - suggested fix
Skip preambles. Lead with findings.
```

### Step 3 — Capture output into the KB

After Gemini returns, write the output to:

```
ai-knowledge-base/raw/gemini/<YYYY-MM-DD>-<slug>.md
```

Template:

```markdown
---
source: gemini
model: <gemini-2.5-pro or whatever was used>
date: <YYYY-MM-DD>
target: <file / module / PR / feature>
scope: <review | bug-hunt | plan | security>
---

## Prior art consulted
- /kb-query: <one-line summary + [[wikilinks]]>
- NotebookLM: <one-line summary, or "n/a">

## Gemini output
<verbatim gemini output, trimmed of preambles>

## Claude synthesis
<1–3 bullets — which findings are load-bearing, which are noise, what to action>
```

Then tell the user: "Findings saved to `<path>`. Run `/kb-ingest` to promote to research, or `/kb-compile` at end of day."

If `ai-knowledge-base/raw/` does not exist, run `/kb-setup` first (standing bootstrap rule).

## When to use Gemini

**Fire Gemini when:**
- Whole-repo sweep / large-context review (hundreds of files)
- Cross-file / cross-doc reasoning (spec + code, design + implementation)
- Multi-module implementation plan
- Multimodal input (screenshot of bug, PDF of design doc — drop into the prompt)
- Claude wants a long-context second opinion distinct from Codex's focused one

**Do NOT fire Gemini for:**
- Trivial one-file fixes Claude handles alone
- Interactive debugging (use `gemini` interactive mode manually, not this skill)
- Edit tasks — always route to Claude + specialist subagents instead
- Anything `/cso` or `/codex` already covers better (narrow security / focused review)

## Invocation methods

### Method 1 — Explicit `/gemini`

```
/gemini review the payment flow across frontend + backend for race conditions
/gemini --model gemini-2.5-pro draft a plan for the multi-tenant migration
/gemini sweep the repo for usages of the deprecated auth helper
```

| Flag | Values | Default |
|---|---|---|
| `--model` | any gemini model id | whatever `gemini` CLI picks |
| `--approval-mode` | default, auto_edit, yolo, **plan** | **plan** (forced on this stack) |
| `--include-directories` | comma-separated paths | cwd only |

### Method 2 — Claude auto-spawns

When Claude judges Gemini would add value (multi-module plan, whole-repo sweep, joint doc+code review), spawn with the grounded prompt from Step 2. Synthesize Gemini's output with Claude's own analysis, then persist via Step 3.

## Prompting patterns (task-specific)

All prompts end with: `Skip preambles. Lead with findings.`

**Whole-repo / long-context review**
```
Review <feature area or module path list> across the whole repo.
Focus ONLY on: <scope — e.g. "race conditions in payment handlers">.
Ignore: style, naming, formatting.
Format: `file:line` - severity (P0/P1/P2) - issue - suggested fix
```

**Cross-file bug hunt**
```
Find bugs across <dir list> where <specific pattern, e.g. "caller assumes X but callee returns Y">.
ONLY report actual bugs — not style.
Format: `file:line` - bug - root cause - suggested fix
```

**Security review (long-context)**
```
Review <target scope> for security vulnerabilities.
Focus ONLY on: auth, injection, data exposure, access control, SSRF, deserialization.
Do NOT suggest style or refactor changes.
Format: `file:line` - severity (P0/P1/P2) - issue
```

**Multi-module implementation plan**
```
Create implementation plan for: <feature>.
Relevant modules: <list>.
Constraints: <existing patterns / Prior art from KB>.
Output:
1. Overview
2. Files to modify (with line ranges) grouped by module
3. Implementation steps in dependency order
4. Cross-module integration points
5. Edge cases
No code samples unless critical.
```

**Spec + code joint review**
```
Read <spec path> alongside <code path(s)>.
Identify: spec requirements not yet implemented, code that contradicts the spec, edge cases the spec does not cover.
Format: `spec-section | file:line` - gap/conflict - recommendation
```

**Design review (Gemini's specialty)**
```
Review the attached screenshot(s) against <component path(s)> and <DESIGN.md / tokens file>.
Critique:
  1. Visual hierarchy — is the primary action obvious, are headings weighted right?
  2. Spacing & rhythm — consistent scale, no magic numbers, aligned to token grid.
  3. Typography — weight / size / line-height adherence to the design system.
  4. Color & contrast — token usage, WCAG AA at minimum, dark-mode parity.
  5. Design-system drift — any inline hex / arbitrary Tailwind values that should be tokens.
  6. Polish gaps — alignment, overflow, empty states, loading states, focus rings.
Ignore: logic, data flow, backend concerns.
Format: `file:line | screenshot-region` - issue - token-aware fix
```

Attach screenshots by passing paths in `--include-directories`, or drop them into the prompt as file references — Gemini reads images natively.

**Design-system drift audit (whole-UI sweep)**
```
Sweep <frontend src dir> for design-system drift against <DESIGN.md / tokens file>.
Flag: hardcoded hex colors, arbitrary Tailwind values (e.g. `w-[437px]`), inline font sizes,
      non-token spacing, bespoke shadows, one-off radii, custom easing curves.
Group findings by severity (P0 brand violation, P1 drift, P2 nit).
Format: `file:line` - violation - token that should replace it
```

## Error handling

**Gemini not installed** →
```
Gemini CLI is not installed.
  brew install gemini-cli      # or: npm install -g @google/gemini-cli
  gemini                       # then follow the auth prompt
Docs: https://geminicli.com/docs
```

**Auth errors** → run `gemini` once interactively to complete OAuth / API-key setup.
**Timeout / rate-limit** → narrow scope, re-run with smaller `--include-directories`.
**Mutation attempt despite plan mode** → escalate, do not override. Claude owns edits.

## Guardrails

- Never run Gemini without Step 1 research.
- Never skip Step 3 capture.
- `--approval-mode plan` is mandatory on this stack — Gemini is read-only here. `--yolo` is forbidden.
- Prefer Claude + specialist subagents for edits. Gemini proposes, Claude executes.
- Output format: always `file:line` references so findings are navigable.
- When Codex and Gemini disagree, surface the conflict to the user — don't silently pick one.
