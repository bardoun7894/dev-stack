---
name: direction
description: Drift check of a repo against its specs and non-negotiables. Report only, never edits code or specs, never auto-reverts. `drift.sh` maps commits to specs/*/ (UNMAPPED = work nobody planned) and marks each non-negotiable rule HAS-CHECK / NO-CHECK; the agent then judges the UNMAPPED commits once and writes a scorecard to specs/_direction/<date>.md. Use at the end of a spec before finishing-a-development-branch, weekly, or on "are we drifting", "direction", "/direction", "هل انحرفنا عن الخطة". After Vercel CEO's "direction" command (AI LABS video y2ifUC9_zuU).
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
   The check match is a keyword heuristic over tests, lint configs, hooks and CI files. Open the named file before trusting a HAS-CHECK.
2. ONE judge pass over the `UNMAPPED` commits only (not the mapped ones). Read the commit subject and file list, and the spec titles. Label each: `in plan` (covered by a spec, just not referenced), `out of plan`, or `unclear`. Do not read whole diffs unless a label is truly unclear.
3. Scorecard:
   - on-plan % = (mapped + `in plan`) / (total commits - housekeeping)
   - unmapped work: count of `out of plan` and `unclear`
   - NO-CHECK non-negotiables: list them
4. Actions, per `out of plan` item: keep and update the spec (name the spec and the line to add), or revert (name the commits). Per NO-CHECK rule: propose the cheapest enforcing check (test, lint rule, hook, CI step).
5. Save the full report (script output + judgement + scorecard + actions) to `specs/_direction/<YYYY-MM-DD>.md` in the target repo.

## Rules

- Report only. Never edit code or specs, never run a revert. The owner decides keep/update/revert.
- A non-negotiable without a check is a wish: surface it every time.
- Do not spawn a reviewer per spec; one judge pass is enough.

## Related

- `retro` audits sessions (process waste); `direction` audits the product against the plan.
- `cso` for security findings, `dogfood` (Breaker pass) for destructive user-level testing.
