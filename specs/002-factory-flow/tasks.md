# Tasks: factory-flow

**Input**: Design documents from `/specs/002-factory-flow/`
**Prerequisites**: plan.md, spec.md

## Phase 1: R1 + R2 + R9 (mediatgb)

- [ ] T001 [P] Write `tests/factory-flow/wip_limit_test.sh` for F5 (TDD red)
- [ ] T002 [P] Write `tests/factory-flow/automerge_test.sh` for F1, F15 (TDD red)
- [ ] T003 Confirm mediatgb CI with `ci-ok` is green on PRs (CI worker)
- [ ] T004 Enable branch protection on main: require ci-ok, admins exempt
- [ ] T005 Implement `lib/prqueue.sh` ticket state from PR state
- [ ] T006 jdelegate: R1 refusal at N=3 and arm auto-merge on implementer exit
- [ ] T007 Implement small `bin/merge-fallback` for repos without CI (F16)
- [ ] T008 Run F1, F5 live on mediatgb

## Phase 2: R5 scoped tests and Actions

- [ ] T010 Write scoped-test check for F10 (TDD red)
- [ ] T011 Scoped test selection on PR, Pest --parallel
- [ ] T012 Full suite on every 5th merge and nightly workflow
- [ ] T013 Update mediatgb AGENTS.md gate rule (Q1 approved)
- [ ] T014 Record median PR-open-to-merge time before and after

## Phase 3: R2a + R3 + R4

- [ ] T020 [P] Write `conflict_test.sh` for F2, F3, F4 (TDD red)
- [ ] T021 [P] Write `sweep_test.sh` for F6, F7, F8, F9 (TDD red)
- [ ] T022 Conflict classifier and Grok call via server-agent.sh
- [ ] T023 Return to same implementer via `jdelegate --resume`
- [ ] T024 `bin/pr-sweep` (48h, 400 lines, 1h fix timer) and timer
- [ ] T025 Close path reopens tasks in the spec; handle pr-review G3 exhaustion notice
- [ ] T026 pr-review: owner and timeout per block reason
- [ ] T027 Clear the current backlog of 36 blocked PRs with the sweep

## Phase 4: R6-R8 and R9 rollout

- [ ] T030 Tokyo registry entry per project (host, user, command)
- [ ] T031 Dry run per project, record date (F11)
- [ ] T032 `bin/deploy-offer`, one batched daily offer
- [ ] T033 Write `drift_test.sh` (F12, TDD red)
- [ ] T034 `install.sh` and `bin/drift-check` with timer
- [ ] T035 Tag test and smoke runs, exclude from failure counts (F13)
- [ ] T036 `bin/daily-digest` stale >48h line (F14)
- [ ] T037 Add PR CI with `ci-ok` to crmAi and lab_chemical
- [ ] T038 Add CI to transport-tms; each repo joins auto-merge after CI green (R9)
