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
| E10 | jdelegate gate-wait used the wrong host (MyContabo) for MediaContabo tickets, causing hours of polling | Fixed today by jdelegate-gate-host; R1/R2 remove polling by moving waiting to GitHub |
| E11 | crmAi and lab_chemical had no CI runs on today's pushes | R9 |
| E9 | Test runs (tabjob/k137/tojob, 80 runs) logged as real agent failures | Noise hides real failures; R8 |

## Owner update 2026-10-30

GitHub Pro; mediatgb auto-merge enabled; a worker is adding sharded GitHub Actions CI on every PR with one required check `ci-ok`; branch protection on main (require ci-ok, admins exempt) follows once green. Answers: Q1 scoped tests at merge and tests move to Actions, 8-CPU dropped unless CI proves insufficient; Q2 = 3; Q3 = mediatgb first.

## Analysis

The 4-CPU server gate (about 2 merges/hour) was the bottleneck. Moving tests to sharded Actions removes the server as the gate and the flock queue with it; GitHub auto-merge replaces the custom merge-queue service, so no new orchestrator is built. Intake is still throttled (R1) by open PRs waiting on auto-merge, and waiting happens in GitHub, not in LLM sessions (E4, E10). Repos without CI keep a small bash fallback until R9 is met. Scoped tests plus a full suite every 5 merges and nightly replace "full gate after each merge".

## Options considered

- Raise the worker limit: rejected, makes the queue longer.
- 8-CPU upgrade: dropped by owner unless CI proves insufficient.
- Custom bash/systemd merge-queue service as primary: replaced by GitHub auto-merge; kept only as fallback.
- LLM-run merge orchestrator: rejected, waiting costs tokens (E4).
