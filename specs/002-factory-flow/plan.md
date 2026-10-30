# Implementation Plan: factory-flow

**Branch**: `spec-002-factory-flow` | **Date**: 2026-10-30 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/002-factory-flow/spec.md`

## Summary

Bound intake by gate capacity and move waiting into a code-only merge-queue service. Rollout order: R1+R2, then R5, then R3+R4, then R6-R8. First project: mediatgb on MediaContabo (Q3). Each phase is shippable alone. Tests first (TDD) as bash fixtures under `tests/factory-flow/`.

Paths below are best-effort and are confirmed against the repo layout at the start of each phase.

## Phase 1: R1 + R2 queue and WIP limit

Files:
- `bin/merge-queue` (new): FIFO loop, ticket state machine, uses gate-run tickets
- `systemd/merge-queue@.service` (new): one instance per project
- `lib/ticket.sh` (new): create, move, list tickets
- `bin/jdelegate` (edit): R1 refusal when ready queue >= N; ticket drop at implementer exit
- `tests/factory-flow/queue_test.sh`, `wip_limit_test.sh` (new)
- `config/factory.env` (new): N, per-project server

Exit: F1, F5 pass on a fixture; mediatgb live on MediaContabo.

## Phase 2: R5 faster gate

Files:
- `bin/merge-queue` (edit): scoped test selection, counter for full suite every 5 merges
- nightly full-suite timer (new)
- mediatgb `ops/test.sh` (edit, in that repo): Pest --parallel, scoped mode
- AGENTS.md rule change in mediatgb, only after Q1 yes

Exit: F9 passes; median merge gate time measured before and after.

## Phase 3: R2a, R3, R4 conflicts, size, blocks

Files:
- `bin/merge-queue` (edit): conflict classifier, Grok call via `server-agent.sh`, return via `jdelegate --resume`
- `bin/pr-sweep` (new) and timer: 48h and 400-line checks, 1h fix timer, close and reopen tasks in the spec
- review bot config (edit): owner and timeout on each block reason
- `tests/factory-flow/conflict_test.sh`, `sweep_test.sh` (new)

Exit: F2, F3, F4, F6, F7, F8 pass.

## Phase 4: R6, R7, R8 deploy, drift, signal

Files:
- Tokyo registry (edit, tokyo repo): host, user, command per project; `tokyo-deploy --dry-run`
- `bin/deploy-offer` (new): one batched daily offer
- `install.sh` (new) and `bin/drift-check` (new) plus timer
- agent run logging (edit): tag test and smoke runs; `bin/daily-digest` (new) for the stale >48h line
- `tests/factory-flow/drift_test.sh`, `signal_test.sh` (new)

Exit: F10-F13 pass.

## Risks

- Q1 not answered: Phase 2 ships Pest --parallel only.
- Ticket store on one server: tickets live on the project server, so each service is independent.
