# Research: factory-flow

Evidence from 2026-10-30. Sources: gate-status, flock lock listing, jdelegate registry, review bot verdicts, Tokyo deploy run log.

## Findings

| # | Finding | Effect |
|---|---------|--------|
| E1 | MediaContabo (4 CPU, 7GB) runs the mediatgb full suite in 20-45 min with 2 heavy slots, about 2 merges/hour | Gate capacity is the bottleneck |
| E2 | 7 merges queued on one flock lock `mediatgb-merge`, oldest 3h24m, random order | Fixed today by dev-stack PR #22 (FIFO tickets, 90m cap on -merge locks); intake still unbounded |
| E3 | Jobs held the merge lock for a 3h vitest and a 170m chain | Cap added in PR #22 |
| E4 | 6 live workers vs limit 3; two polled 3h for a translation key | LLM time burned while waiting; motivates R1, R2 |
| E5 | 36 open PRs blocked by review bot: verdict-block 25, repo-no-automerge 8, no-second-reviewer 5; some 22 days old | No owner or timeout on blocks; motivates R3, R4 |
| E6 | 28 Tokyo deploy runs failed: ran as tokyo-agent without root; prod moved to MediaContabo 2026-10-28 | Fixed today (tokyo 72f7d35); motivates R6 |
| E7 | GodHome incidents never resolved | Fixed today (godhome 0624258); R8 |
| E8 | Installed gate-run and server-health differed from repo copies | Motivates R7 |
| E9 | Test runs (tabjob/k137/tojob, 80 runs) logged as real agent failures | Noise hides real failures; R8 |

## Analysis

Intake is bounded by workers (3), output by the gate (about 2 merges/hour). Work that cannot merge sits as open PRs and ages into conflicts, which cost more rework. Throttling intake at the gate capacity (R1) and moving waiting out of LLM sessions (R2) addresses the pile-up directly. Gate time is cut by scoped tests (R5), trading the owner rule "full gate after each merge" for a full suite every 5 merges and nightly. This needs the owner decision Q1.

## Options considered

- Raise the worker limit: rejected, makes the queue longer.
- Only the 8-CPU upgrade: helps about 2x, does not bound intake. Kept as optional, paired with scoped tests.
- LLM-run merge orchestrator: rejected, waiting costs tokens and caused E4.
