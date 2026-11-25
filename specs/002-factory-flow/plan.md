# Implementation Plan: factory-flow

**Branch**: `spec-002-factory-flow` | **Date**: 2026-10-30 (revised GitHub-first) | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/002-factory-flow/spec.md`

## Summary

Let GitHub do the merging: sharded Actions CI with `ci-ok`, auto-merge gated by ci-ok and the pr-review verdict. Dev-stack adds the intake limit, sweeps, deploy path and ops hygiene. First project: mediatgb (Q3). Each phase is shippable alone. Tests first as bash fixtures under `tests/factory-flow/`. Paths are best-effort; confirm at the start of each phase.

## Phase 1: R1 + R2 + R9 (mediatgb) WIP limit and auto-merge

Files:
- mediatgb `.github/workflows/ci.yml` (owned by the CI worker): sharded jobs, aggregate job `ci-ok`
- GitHub settings: branch protection on main (require ci-ok, admins exempt) once CI is green
- `bin/jdelegate` (edit): R1 count of open PRs with auto-merge armed >= N refuses; implementer exit arms `gh pr merge --auto --squash`
- `lib/prqueue.sh` (new): list waiting PRs per project, derive ticket state
- `bin/merge-fallback` (new, small): FIFO via gate-run tickets for repos without CI (reuses PR #22 behaviour)
- `config/factory.env` (new): N, per-project repo
- `tests/factory-flow/wip_limit_test.sh`, `automerge_test.sh` (new)

Exit: F1, F5, F15, F16 pass on mediatgb.

## Phase 2: R5 scoped tests and Actions

Files:
- mediatgb workflow (edit): scoped test selection on PR, Pest --parallel
- full-suite workflow on every 5th merge (counter) and nightly schedule (new)
- mediatgb AGENTS.md rule change "full gate after each merge" -> scoped + periodic full (Q1 approved)
- measure PR-open-to-merge time before and after; revisit 8-CPU only if CI is insufficient

Exit: F10 passes.

## Phase 3: R2a + R3 + R4 conflicts, size, blocks

Files:
- `bin/pr-sweep` (new) and timer: red ci-ok return, conflict classifier, Grok call via `server-agent.sh`, `jdelegate --resume`, 48h and 400-line checks, 1h fix timer, G3 exhaustion close, reopen tasks in the spec
- pr-review config (edit): owner and timeout per block reason; read G3 notice
- `tests/factory-flow/conflict_test.sh`, `sweep_test.sh` (new)

Exit: F2, F3, F4, F6, F7, F8, F9 pass.

## Phase 4: R6-R8 and R9 rollout deploy, drift, signal, CI everywhere

Files:
- Tokyo registry (tokyo repo): host, user, command per project; `tokyo-deploy --dry-run`
- `bin/deploy-offer` (new): one batched daily offer
- `install.sh`, `bin/drift-check` (new) plus timer
- agent run logging: tag test and smoke runs; `bin/daily-digest` (new)
- CI with `ci-ok` for crmAi, lab_chemical, transport-tms, then each joins auto-merge

Exit: F11-F15 pass.

## Risks

- CI minutes cost on private repos: watch usage under Pro limits.
- Auto-merge needs branch protection with required checks, else it merges immediately.
- Admins exempt: owner pushes bypass ci-ok by design.
