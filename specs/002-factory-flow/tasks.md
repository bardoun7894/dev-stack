# Tasks: factory-flow

**Input**: Design documents from `/specs/002-factory-flow/`
**Prerequisites**: plan.md, spec.md

## Phase 1: R1 + R2 queue and WIP limit

- [ ] T001 [P] Write `tests/factory-flow/queue_test.sh` for F1 (TDD red)
- [ ] T002 [P] Write `tests/factory-flow/wip_limit_test.sh` for F5 (TDD red)
- [ ] T003 Implement `lib/ticket.sh` state machine
- [ ] T004 Implement `bin/merge-queue` FIFO loop on gate-run tickets
- [ ] T005 Add `systemd/merge-queue@.service`
- [ ] T006 Add R1 refusal and ticket drop to jdelegate
- [ ] T007 Deploy to mediatgb on MediaContabo and run F1, F5 live

## Phase 2: R5 faster gate

- [ ] T010 Write `tests/factory-flow/scoped_test.sh` for F9 (TDD red)
- [ ] T011 Implement scoped test selection and 5-merge counter
- [ ] T012 Add nightly full-suite timer
- [ ] T013 Enable Pest --parallel in mediatgb `ops/test.sh`
- [ ] T014 Record median gate time before and after
- [ ] T015 After owner yes on Q1, update the mediatgb gate rule

## Phase 3: R2a, R3, R4 conflicts, size, blocks

- [ ] T020 [P] Write `conflict_test.sh` for F2, F3, F4 (TDD red)
- [ ] T021 [P] Write `sweep_test.sh` for F6, F7, F8 (TDD red)
- [ ] T022 Implement conflict classifier and Grok call via server-agent.sh
- [ ] T023 Implement return via `jdelegate --resume`
- [ ] T024 Implement `bin/pr-sweep` (48h, 400 lines, 1h fix timer) and timer
- [ ] T025 Close path reopens tasks in the spec
- [ ] T026 Review bot: owner and timeout per block reason
- [ ] T027 Clear the current backlog of 36 blocked PRs with the sweep

## Phase 4: R6-R8 deploy, drift, signal

- [ ] T030 Tokyo registry entry per project (host, user, command)
- [ ] T031 Dry run per project, record date in the registry (F10)
- [ ] T032 Implement `bin/deploy-offer`, one batched daily offer
- [ ] T033 Write `drift_test.sh` (F11, TDD red)
- [ ] T034 Implement `install.sh` and `bin/drift-check` with timer
- [ ] T035 Tag test and smoke runs, exclude from failure counts (F12)
- [ ] T036 Implement `bin/daily-digest` stale >48h line (F13)
- [ ] T037 Extend to crmai and transport-tms on MyContabo (Q3)
