---
name: kb-dev
description: One-company dev team in a single skill. Unified end-to-end pipeline that chains the kb-* knowledge base, GitHub Spec Kit, and obra/superpowers skills into a complete workflow — from research → spec → plan → tasks → implement (with orchestrator delegation) → verify → review → merge → knowledge capture. TRIGGER PROACTIVELY when the user says "new feature", "build X", "implement Y", "let's start a spec", "ship this", or gives any non-trivial engineering request. Routes the user through the right sub-skill at each phase; do not reimplement any phase yourself. For small one-off edits, run solo-mode; for multi-task features, delegate to dispatching-parallel-agents with an Opus orchestrator and Sonnet workers.
allowed-tools: Bash Read Write Edit Glob Grep Agent Skill
---

# kb-dev — the unified dev-team workflow

This skill is the **single entry point** for any non-trivial engineering task. It does not do the work itself. It orchestrates the other skills you already have installed:

| Phase                      | Sub-skill                                                                              | Model          |
|----------------------------|----------------------------------------------------------------------------------------|----------------|
| 0. Ground in prior art     | `/kb-query`                                                                            | (no agent)     |
| 1. Brainstorm options      | `brainstorming` (obra)                                                                 | inline         |
| 2. Pre-spec KB research    | `/kb-spec pre` → `/speckit.specify`                                                    | inline         |
| 3. Architectural plan      | `/kb-spec plan` → `/speckit.plan` → `writing-plans` (obra)                             | inline         |
| 4. Task breakdown          | `/kb-spec tasks` → `/speckit.tasks`                                                    | inline         |
| 5a. Implement (solo)       | `executing-plans` (obra) in current session                                            | Sonnet         |
| 5b. Implement (fan-out)    | `dispatching-parallel-agents` + `subagent-driven-development` (obra)                   | Opus → Sonnet  |
| 6. Test-first discipline   | `test-driven-development` (obra) inside each worker                                    | Sonnet         |
| 7. Debug if something fails| `systematic-debugging` (obra)                                                          | Sonnet         |
| 8. Verify before claiming  | `verification-before-completion` (obra)                                                | Sonnet         |
| 9. Request review          | `requesting-code-review` (obra)                                                        | Sonnet         |
| 10. Apply review           | `receiving-code-review` (obra)                                                         | Sonnet         |
| 11. Finish branch          | `finishing-a-development-branch` (obra) — optional: `using-git-worktrees`              | inline         |
| 12. Capture knowledge      | `/kb-spec post` → `/kb-docs-sync` → `/kb-compile` → `/kb-lint`                         | inline         |

## Decision: solo vs fan-out

Read `specs/<feature>/tasks.md`. If it has:
- **≤ 3 tasks** or **a single dependency chain** → **solo mode** (phase 5a). One `executing-plans` run in-session.
- **≥ 4 independent tasks** OR the user says "parallelize" / "fan-out" / "team" → **fan-out mode** (phase 5b). Spawn an Opus orchestrator via the `Agent` tool with `subagent_type` set to a general-purpose agent loaded with the `dispatching-parallel-agents` skill. The orchestrator then spawns one Sonnet worker per task group, each running `subagent-driven-development`.

If unsure, ask once: "Solo or fan-out?"

## Mandatory sequencing rules

1. **Never skip phase 0** — always run `/kb-query` first, even if you think you know the answer. The KB has history you will not remember.
2. **Never skip phase 8** — `verification-before-completion` runs the full test suite and the user's definition of done. Saying "done" without it is the most common failure mode.
3. **Capture knowledge in phase 12** — without `/kb-spec post` + `/kb-compile`, the next feature will not benefit from what you just learned.
4. **Fan-out guardrail** — never spawn more than 4 parallel workers without user confirmation. Cost and debugging difficulty grow non-linearly past that.

## Model assignment

- **Opus** → the orchestrator only. Used when fan-out mode is chosen and the orchestrator must decompose tasks.md into work packets.
- **Sonnet** → the default for all worker agents, implementation, debugging, review.
- **Haiku** → cheap one-shot lookups the orchestrator needs (file existence, single-file read summaries, "does this symbol exist"). Spawn via `Agent(model: "haiku", ...)`.

## Invocation

| Trigger phrase                                       | What kb-dev does                                                  |
|------------------------------------------------------|-------------------------------------------------------------------|
| "new feature X"                                      | Run phases 0 → 4, pause for solo/fan-out decision                 |
| "implement the spec at specs/NNN"                    | Run phase 0, then jump to phase 5, then 6–12                      |
| "fix bug Y" (< 30 LOC)                               | Run phase 0, then solo-mode phase 5a straight through to 12       |
| "ship this branch"                                   | Run phases 9 → 12                                                 |
| "debug this"                                         | Run `systematic-debugging` directly                               |
| "brainstorm X"                                       | Run `brainstorming` directly                                      |

## What kb-dev explicitly does NOT do

- It does not rewrite `kb-spec`, `kb-query`, or any other sub-skill. It only sequences them.
- It does not replace `/speckit.*`. Spec Kit still owns spec/plan/tasks file authoring. kb-dev just wires the KB research steps before each Spec Kit call and the knowledge capture after.
- It does not silently run destructive operations. Merging, force-pushing, dropping migrations, deleting branches — all pause for user confirmation regardless of the current phase.

## Relationship to the standing-rule hook

The global `UserPromptSubmit` hook at `~/.claude/hooks/user-prompt-kb-check.sh` already reminds you to run `/kb-query` and `/kb-spec <phase>` before each matching action. kb-dev is the **explicit** codification of that rule as a complete skill — use it when the user wants "the whole pipeline" instead of cherry-picking phases manually.
