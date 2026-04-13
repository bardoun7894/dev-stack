---
name: kb-dev
description: Unified 12-phase dev pipeline. Chains kb-query → brainstorming → kb-spec → writing-plans → implement (solo or fan-out) → TDD → verify → review → finish → kb capture. Use for any non-trivial feature/build/ship request. Read SKILL.md for the phase table.
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

## Connect-the-dots: skill relations map

This is the canonical map of how all 36 installed skills relate to each other. kb-dev is the hub — every other skill is reachable through one of its phases or as an explicit standalone branch.

```
                              ┌─────────────────────────┐
                              │   USER PROMPT (any)     │
                              └────────────┬────────────┘
                                           │
                          ┌────────────────┴────────────────┐
                          │  UserPromptSubmit hook fires    │
                          │  - bootstraps git/kb/speckit    │
                          │  - injects standing-rule reminder│
                          └────────────────┬────────────────┘
                                           │
              ┌────────────────────────────┼────────────────────────────┐
              │                            │                            │
              ▼                            ▼                            ▼
    ┌──────────────────┐       ┌──────────────────────┐     ┌──────────────────┐
    │ trivial Q/cmd    │       │  spec-only request   │     │ feature/build/   │
    │ (no skills)      │       │  "spec out X"        │     │ ship/fix request │
    └──────────────────┘       └─────────┬────────────┘     └────────┬─────────┘
                                         │                           │
                                         ▼                           ▼
                              ┌────────────────────┐       ┌──────────────────┐
                              │   /kb-spec only    │       │     /kb-dev      │
                              │ (phases 0,2,3,4)   │       │  (full pipeline) │
                              └─────────┬──────────┘       └────────┬─────────┘
                                        │                           │
                                        └─────────────┬─────────────┘
                                                      │
                                                      ▼
              ┌──────────────────────────────────────────────────────────────┐
              │                  Phase 0: /kb-query                          │
              │  → cites [[wikilinks]] from prior decisions                  │
              └──────────────────────────────┬───────────────────────────────┘
                                             │
                                             ▼
              ┌──────────────────────────────────────────────────────────────┐
              │            Phase 1: brainstorming (obra)                     │
              │  → option exploration, before committing to a direction     │
              └──────────────────────────────┬───────────────────────────────┘
                                             │
                                             ▼
              ┌──────────────────────────────────────────────────────────────┐
              │   Phase 2: /kb-spec pre  →  /speckit.specify  →  spec.md     │
              └──────────────────────────────┬───────────────────────────────┘
                                             │
                                             ▼
              ┌──────────────────────────────────────────────────────────────┐
              │  Phase 3: /kb-spec plan  →  /speckit.plan                    │
              │           →  writing-plans (obra)  →  plan.md                │
              └──────────────────────────────┬───────────────────────────────┘
                                             │
                                             ▼
              ┌──────────────────────────────────────────────────────────────┐
              │  Phase 4: /kb-spec tasks  →  /speckit.tasks  →  tasks.md     │
              └──────────────────────────────┬───────────────────────────────┘
                                             │  AUTO-CONTINUE
                                             ▼
                          ┌──────────────────────────────────┐
                          │  Read tasks.md. Decide:          │
                          │  ≤3 tasks  →  solo               │
                          │  ≥4 indep  →  fan-out            │
                          └────────┬────────────────┬────────┘
                                   │                │
                          ┌────────┘                └────────┐
                          ▼                                   ▼
              ┌──────────────────────┐         ┌──────────────────────────────┐
              │ Phase 5a: SOLO       │         │ Phase 5b: FAN-OUT            │
              │ executing-plans      │         │ Opus orchestrator (Agent)    │
              │ in current session   │         │  ↓                           │
              │ Sonnet               │         │ dispatching-parallel-agents  │
              └──────────┬───────────┘         │  ↓                           │
                         │                     │ N × Sonnet workers           │
                         │                     │  each running:               │
                         │                     │  subagent-driven-development │
                         │                     │  Haiku for cheap lookups     │
                         │                     └──────────┬───────────────────┘
                         │                                │
                         └────────────────┬───────────────┘
                                          │
                                          ▼
              ┌──────────────────────────────────────────────────────────────┐
              │  Phase 6: test-driven-development (obra) — inside each       │
              │           worker. Red-Green-Refactor before each commit.     │
              └──────────────────────────────┬───────────────────────────────┘
                                             │
                                             ▼
              ┌──────────────────────────────────────────────────────────────┐
              │  Phase 7: systematic-debugging (obra) — only fires on test   │
              │           failure or unexpected behavior                     │
              └──────────────────────────────┬───────────────────────────────┘
                                             │
                                             ▼
              ┌──────────────────────────────────────────────────────────────┐
              │  Phase 8: verification-before-completion (obra)              │
              │  → runs full test suite + DoD checks before claiming done    │
              └──────────────────────────────┬───────────────────────────────┘
                                             │
                                             ▼
              ┌──────────────────────────────────────────────────────────────┐
              │  Phase 9: requesting-code-review (obra)                      │
              │  Phase 10: receiving-code-review (obra)                      │
              └──────────────────────────────┬───────────────────────────────┘
                                             │
                                             ▼
              ┌──────────────────────────────────────────────────────────────┐
              │  Phase 11: finishing-a-development-branch (obra)             │
              │  Optional: using-git-worktrees (obra) for isolation          │
              └──────────────────────────────┬───────────────────────────────┘
                                             │
                                             ▼
              ┌──────────────────────────────────────────────────────────────┐
              │  Phase 12: KNOWLEDGE CAPTURE (auto-continue)                 │
              │  /kb-spec post  →  /kb-docs-sync  →  /kb-compile  →  /kb-lint│
              │  → next feature benefits from what we just learned           │
              └──────────────────────────────────────────────────────────────┘
```

### Auto-continue rules (no user nudge required)

These transitions fire automatically. Do NOT pause to ask the user; just continue.

| From          | To                  | Trigger                                                        |
|---------------|---------------------|----------------------------------------------------------------|
| Phase 4 done  | Phase 5 (solo/fan-out) | `tasks.md` exists and has at least one task                  |
| Phase 5 done  | Phase 6             | Code written, before any commit                                |
| Phase 6 fail  | Phase 7             | Any test red                                                   |
| Phase 7 done  | Phase 6             | Bug fixed, re-run tests                                        |
| Phase 6 green | Phase 8             | All tests pass                                                 |
| Phase 8 done  | Phase 9             | Verification passed                                            |
| Phase 9 done  | Phase 10            | Review feedback received                                       |
| Phase 10 done | Phase 11            | Feedback applied                                               |
| Phase 11 done | Phase 12            | Branch finished                                                |

The **only** transitions that pause for the user are:
- Phase 4 → 5 if tasks.md is borderline (3-4 tasks) and solo/fan-out is genuinely ambiguous
- Phase 11 → merge to main (destructive, always confirm)
- Any failure mode that needs a design call

### UI/frontend skills — wired into Phase 5 implementation (auto-routing)

When Phase 5 hits a UI/frontend task, route to the right specialist skill instead of writing CSS by hand. These are NOT standalone — they fire automatically from inside the worker agent based on what the task says:

| Task content contains…                                                | Auto-route to                |
|-----------------------------------------------------------------------|------------------------------|
| "build", "create", "design" + "page" / "component" / "landing"        | `frontend-design`            |
| "responsive", "mobile", "breakpoint", "viewport", "tablet", "iPad"    | `adapt`                      |
| "animate", "transition", "motion", "hover effect", "micro-interaction"| `animate`                    |
| "polish", "alignment", "spacing", "finishing touches", "looks off"    | `polish`                     |
| "consistent", "design system", "tokens", "drift"                      | `normalize`                  |
| "harden", "edge case", "i18n", "overflow", "production-ready"         | `harden`                     |
| "slow", "laggy", "janky", "bundle size", "perf"                       | `optimize`                   |
| "a11y", "accessibility", "audit", "lighthouse"                        | `audit`                      |
| "confusing copy", "label", "error message", "microcopy"               | `clarify`                    |
| "too bold", "too loud", "calmer", "overstimulating"                   | `quieter`                    |
| React / Next.js component or perf work                                | `vercel-react-best-practices`|

These routing rules apply both to **solo mode** (Phase 5a — current session) and **fan-out mode** (Phase 5b — each Sonnet worker spawns the relevant UI skill inside its own context). The orchestrator does not need to invoke them; the worker recognizes its task and pulls in the matching skill.

### Standalone branches (only on explicit user invocation)

These never auto-fire from kb-dev — the user must explicitly request them:

| Skill          | Trigger                                              | Why standalone                            |
|----------------|------------------------------------------------------|-------------------------------------------|
| `grill-me`     | "grill me", "stress-test this", "poke holes"         | High-friction; opt-in only                |
| `tech-company` | "act as a tech company", "delegate to engineers"     | Alternative orchestrator pattern          |
| `kb-ingest`    | "ingest these docs", file dropped in `raw/`          | Manual document ingest                    |
| `kb-publish`   | "publish KB to NotebookLM"                           | Manual publishing                         |
| `kb-lint`      | "audit the KB", periodic on demand                   | Audit, not workflow                       |
| `writing-skills` | "create a new skill", "edit a skill"               | Skill authoring meta-tool                 |
| `using-superpowers` | Auto-loaded at session start by obra              | Bootstrapper, not in pipeline             |

### Cross-references (which skill calls which)

- `kb-dev` calls everything in the main pipeline.
- `kb-spec` calls `kb-query` (reads prior art) and `kb-docs-sync` (in `post` mode).
- `dispatching-parallel-agents` calls the `Agent` tool with `subagent-driven-development` loaded into each worker.
- `executing-plans` calls `test-driven-development` for each task and `verification-before-completion` at the end.
- `requesting-code-review` reads the diff and writes a review request; `receiving-code-review` reads incoming feedback and routes it back to `executing-plans` for fixes.
- `kb-compile` reads `daily/` logs (auto-captured by the SessionStart hook) and writes to `knowledge/concepts/` + `knowledge/connections/`.
- `kb-docs-sync` mirrors `specs/`, `plans/`, `CLAUDE.md`, `README.md` into `knowledge/sources/`.

This is the complete map. If a skill is not on it, it is either a meta-tool (writing-skills, using-superpowers) or a user-utility (loop, schedule, update-config, keybindings-help) and is not part of the dev pipeline.
