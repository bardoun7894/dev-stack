---
name: direction
description: Drift check of a repo against its specs and non-negotiables. Report only, never edits code or specs, never auto-reverts. `drift.sh` maps commits to specs/*/ (UNMAPPED = work nobody planned) and marks each non-negotiable rule HAS-CHECK / NO-CHECK; the agent then judges the UNMAPPED commits once and writes a scorecard to specs/_direction/<date>.md. Use at the end of a spec before finishing-a-development-branch, weekly, or on "are we drifting", "direction", "/direction", "هل انحرفنا عن الخطة". `/direction --sweep` finds stale notes, docs, memory and plans that can derail agents ("sweep", "stale context", "old TODOs", "clean up old plans"). After Vercel CEO's "direction" command (AI LABS video y2ifUC9_zuU).
allowed-tools: Bash Read Write Grep Glob
---

# direction: are we still building the plan?

Agents make building cheap, so every idea becomes a feature. Volume of work says nothing about whether it moves toward the plan. This skill checks the work against `specs/` and the non-negotiables.

## When

- End of a spec, before `finishing-a-development-branch` (kb-dev phase 11).
- Weekly, or after a long autonomous run.
- "are we drifting", "direction", "/direction", "هل انحرفنا عن الخطة".

## Steps

1. Mechanical pass, zero AI:
   ```bash
   bash ~/.claude/skills/direction/scripts/drift.sh <repo> [--since <git-ref>]
   ```
   Default range: merge-base with main/master, else the last 30 commits. Output is markdown: specs with open/done task counts, every commit mapped to a spec (by spec name or number in the subject, files under `specs/<dir>/` (most files wins), a backticked file path in that spec's `tasks.md` (`task-path`), a unique T-number, or the branch name) or `UNMAPPED`. Housekeeping commits (only `ai-knowledge-base/`, `specs/_session/`, `specs/_direction/`, `okf/` or `docs/*.md` files, or subjects `docs(kb)` / `docs(specs)` / `chore(kb)`) get their own HOUSEKEEPING count and are not judged. The non-negotiables are `HAS-CHECK` / `NO-CHECK`.
   The check match is a keyword heuristic over candidate files only: tests, CI workflows, lint/analyzer configs and hooks. Docs, `*.md`, `ai-knowledge-base/`, `okf/`, `reports/`, `specs/` and `node_modules/`/`vendor/` never count as a check.
2. ONE judge pass over the `UNMAPPED` commits only (not the mapped ones). Read the commit subject and file list, and the spec titles. Label each: `in plan` (covered by a spec, just not referenced), `out of plan`, or `unclear`. Do not read whole diffs unless a label is truly unclear.
   Also open each HAS-CHECK file named in the non-negotiables table and confirm it actually enforces that rule. If it only mentions the keywords, report that rule as WEAK-CHECK, not HAS-CHECK.
3. **Spec-to-code symbol & contract drift pass (EGM drift check)**:
   For active `specs/*/` (and any folder `README.md` / `EGM.md` contracts with `Interface`/`Invariants` sections):
   - Read the spec (`spec.md`, `plan.md`, `system-design.md`) and list specific routes, models/fields, invariants, and files promised.
   - Verify the actual source files (like `/egm:egm-drift-report`): flag **Missing Features** (described in spec, absent in code), **Incomplete Models** (missing fields), **Logic Shortcuts** (hardcoded values or missing invariants like deletion guards on sold items), and **Architectural Divergence**. Report only discrepancies.
4. Scorecard:
   - on-plan % = (mapped + `in plan`) / (total commits - housekeeping)
   - unmapped work: count of `out of plan` and `unclear`
   - spec-to-code divergences: count of missing features / invariants / model fields found in step 3
   - NO-CHECK non-negotiables: list them
   - WEAK-CHECK non-negotiables: list them, with the file that only mentions the rule
5. Actions, per `out of plan` item or spec-to-code divergence: keep and update the spec (name the spec and the line to add), or fix/revert code (name the file:line or commits). Per NO-CHECK rule: propose the cheapest enforcing check (test, lint rule, hook, CI step).
6. Save the full report (script output + judgement + symbol/invariant drift + scorecard + actions) to `specs/_direction/<YYYY-MM-DD>.md` in the target repo.

## --sweep: stale context that derails agents

Agents read old TODOs, plans, rule files and memory as orders (Google's "side quests": in their study, more than 4 in 5 side quests were unasked, and they cost 77% more tokens; AI LABS JhZB3spnuIY, 2026-11-17). `--sweep` finds them and reports. It never fixes, moves or archives anything.

1. Candidates, zero AI:
   ```bash
   python3 ~/.claude/skills/direction/scripts/sweep.py <repo> [--memory ~/.claude/projects/<slug>/memory] [--no-gh]
   ```
   Kinds: `NOTE-CLOSED` (a TODO/FIXME naming a closed issue), `NOTE-OLD` (a TODO/FIXME untouched for more than 365 days), `DOC-PATH` (CLAUDE.md, AGENTS.md, README.md or docs/ name a repo path that is gone), `MEMORY-PATH` (a memory note names a repo path that is gone), `SPEC-OPEN` (an open T-task in a spec whose later tasks are merged).
2. ONE verifier subagent, fresh context. It gets only the candidate lines: no opinion of yours, and no "these look stale". For each claim it checks the evidence itself (`git log -S`, `git log --follow`, `gh issue view`, `ls`, reading the code) and labels it:
   - `STALE`: the note and its reason are both gone. For a TODO, the issue is closed AND the code it warns about is gone or fixed; a warning that still guards live code is `KEEP`.
   - `KEEP`: still true or still guarding something.
   - `CONFLICT`: a rule, memory note or plan disagrees with the code, but it may be a deliberate decision the code has not caught up with yet. The owner decides.
3. Save the report to `specs/_direction/<YYYY-MM-DD>-sweep.md`: the candidate list, each label with its one-line evidence, then the actions. The actions are: delete the note, update the doc line, or drop the memory entry (each named by file:line), and `CONFLICT` items as questions.
4. The owner approves the items. Only then do you apply them, in a normal commit, and only the approved items. Memory entries: update or delete the memory file and its `MEMORY.md` line.

## Rules

- Report only. Never edit code or specs, never run a revert. The owner decides keep/update/revert. With `--sweep` too: nothing is archived or deleted before the owner approves it.
- A non-negotiable without a check is a wish: surface it every time.
- Do not spawn a reviewer per spec; one judge pass is enough.

## Related

- `retro` audits sessions (process waste); `direction` audits the product against the plan.
- `cso` for security findings, `dogfood` (Breaker pass) for destructive user-level testing.
