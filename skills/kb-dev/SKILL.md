---
name: kb-dev
description: Unified dev pipeline, split by context not by role. kb-query, spec, ONE implementer per spec, fresh reviewer, fresh verifier on the user-flow matrix, finish, KB capture. Use for any non-trivial feature/build/ship request.
allowed-tools: Bash Read Write Edit Glob Grep Agent Skill
---

# kb-dev: entry point for non-trivial engineering work

Rule (owner 2026-10-27, CLAUDE.md "WORK SPLIT"): split work by context, not by role. No persona roles, no packets, no per-task tickets. Orchestrator lifecycle modelled on Ray Amjad's task-lifecycle (no Codex step: no OpenAI).

## Phases (full table with models: `references/phase-table.md`)

| # | Phase | How |
|---|-------|-----|
| 0 | Prior art | `/kb-query` |
| 1 | Brainstorm | `brainstorming` |
| 2 | Spec | `/kb-spec pre` then `/speckit.specify`; research via `jdelegate --role researcher` (question only) into `research.md` |
| 2c | System design | new apps only: `system-design`, owner approves D/Q codes |
| 3 | Plan | `/kb-spec plan` then `/speckit.plan`, `writing-plans` |
| 4 | Tasks | `/kb-spec tasks` then `/speckit.tasks`; add the "Done when" section |
| 4b | Branch | `git checkout -b <NNN-short-name>`, never on main |
| 5 | Implement | ONE implementer per spec (below) |
| 6 | Tests | TDD inside the implementer; 6a: list checks in plain words, wait for user OK, `lock-checks approve <tests>`, workers run `lock-checks verify` after each round (failing verify = round undone) |
| 7 | Debug | `systematic-debugging`, inside the implementer |
| 8 | Verify | fresh verifier on the flow matrix; UI web: `jev-browse --flows` first; mobile: `npx e2e run` |
| 9 | Review | `jev-review diff` screen, then fresh reviewer (below); PR brief via `pr-pipeline` L3 |
| 10 | Apply | `receiving-code-review`; fixes go to the same implementer; `/direction` drift check |
| 11 | Finish | `finishing-a-development-branch`, always ends in a PR; run the Phase 11 gate |
| 12 | Capture | `/kb-spec post`, `/kb-docs-sync`, `/kb-compile`, `/kb-lint` |

Jev down (402): jev and jdelegate fall back to local Laya; `jev-browse` and `jev-review` exit 3, use the normal LLM path.
Detail: `references/phase-gates.md` (branch rule, e2e suites, lock-checks, PR gate).

## Implementer / reviewer / verifier loop

1. **Implementer:** one `jdelegate --cwd <repo> --name <spec> "<brief>"` worker builds the whole spec in one context. `specs/NNN/tasks.md` is its checklist (tick with merge SHA), not tickets. Never split one spec into parallel workers.
2. **Reviewer:** fresh context, spec + diff only (`jdelegate --role reviewer` or `/code-review`). One reviewer per review (owner 2026-11-06): the first model with quota in jdelegate's chain, no second reviewer. Code review: Opus 5.5 at medium. Deep review (auth, money, migrations, security, T4, or `--deep`): Opus 5.5 at high. Arabic-language review: Gemini 4 Argon (`agy/gemini-4-argon-high`). GPT is not in any review chain until a Sol-capable codex plan exists (gpt-5.6-sol is refused on the ChatGPT login); GPT never implements or orchestrates. P0/P1 findings go to the implementer's same session. Max 1 review + 1 fix round.
3. **Verifier:** fresh context, only the spec's user-flow matrix. Drives each flow as a user on a real non-prod app, resets DB/state between flows, writes evidence per flow. Independent flows may run in parallel. Failures go to the same implementer, then re-verify (max 1 fix round).
   Outcomes: passed; ran wrong (back to implementer); could not boot (report unverified, no fix loop); unreachable (report, ask owner).
4. Parallelism only across separate specs/projects, verify flows, research.

Review and verify detail: `references/review-verify.md`.

## Done when (required in every spec.md/tasks.md)

A "Done when" section listing: tests green, locked checks verified, and the **user-flow matrix** (one row per flow: start state, user steps, expected end state, rows written, outside side effects). No matrix, no verify, no "done".

## Other references

`references/invocation.md` (trigger phrases EN/AR, exclusions) · `references/skill-map.md` (skill relations, UI auto-routing), `references/handoff-matrix.md`, `references/ui-routing.md` · `references/fanout-retired.md` (old NIU/roster, retired).
