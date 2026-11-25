# Feature Specification: factory-flow

**Feature Branch**: `spec-002-factory-flow`  
**PR**: #24  
**Merged**: TBD  
**Created**: 2026-10-30  
**Status**: Draft (revised 2026-10-30 after owner answers, GitHub-first)  
**Input**: The agent software factory (jdelegate workers -> PR review bot -> merge -> deploy via tokyo-deploy) piles up because work enters faster than the test gate finishes it. Owner update 2026-10-30: GitHub Pro, mediatgb auto-merge enabled, sharded GitHub Actions CI with one required check `ci-ok` in progress, branch protection on main (require ci-ok, admins exempt) to follow once CI is green. Includes spec and Phase 1 implementation (WIP limit, prqueue, auto-merge arming and merge-fallback).

## User Scenarios & Testing

### User Story 1 - Implementer opens a PR and exits (Priority: P1)

An implementer finishes a branch, opens a PR, enables `gh pr merge --auto --squash` and exits. GitHub merges the PR once `ci-ok` is green and the pr-review verdict is pass. No LLM and no server lock while waiting.

**Why this priority**: removes the pile-up and workers that poll for hours.

**Independent Test**: open three PRs on a fixture repo with CI; they merge once green, and no jdelegate process is alive while they wait.

**Acceptance Scenarios**:

1. **Given** a repo with CI and auto-merge, **When** an implementer opens a PR, **Then** the ticket goes building -> ready (auto-merge armed) -> merged -> deploy-offered with no worker alive.
2. **Given** a PR with red `ci-ok`, **When** CI fails, **Then** the PR is not merged and returns to its implementer.

### User Story 2 - Too many PRs waiting stops new build work (Priority: P1)

**Why this priority**: work must not enter faster than CI and review finish it.

**Independent Test**: arm N fixture PRs; `jdelegate` for a build role on that project exits non-zero with a reason.

**Acceptance Scenarios**:

1. **Given** project P has >= N open PRs waiting on auto-merge, **When** a build worker is requested for P, **Then** jdelegate refuses and names the count.
2. **Given** the count drops below N, **When** the request is repeated, **Then** it is accepted.

### User Story 3 - Red CI or code conflict returns to the same implementer (Priority: P1)

**Acceptance Scenarios**:

1. **Given** red `ci-ok`, **When** the sweep sees it, **Then** the PR goes back to the same implementer via `jdelegate --resume`.
2. **Given** a trivial conflict (lockfile, lang/*.json, generated file), **When** detected, **Then** one Grok 4.7 call via server-agent.sh resolves it, CI re-runs and auto-merge completes.
3. **Given** a code conflict, **When** detected, **Then** the PR returns to the same implementer.

### User Story 4 - Stale work and blocks have owners and timeouts (Priority: P2)

**Acceptance Scenarios**:

1. **Given** a PR older than 48h without progress, **When** the daily sweep runs, **Then** it returns to its implementer or is closed with its tasks reopened in the spec.
2. **Given** verdict-block, **When** pr-review posts it, **Then** the same implementer gets one fix round within 1h, else the PR is closed and tasks reopened.
3. **Given** pr-review posts its G3 exhaustion notice (review and fix rounds used), **When** the sweep sees it, **Then** the PR is closed and tasks reopened without a further round.

### User Story 5 - Deploy and ops hygiene (Priority: P2)

**Acceptance Scenarios**:

1. **Given** merges happened today, **When** the daily offer runs, **Then** the owner gets one batched Deploy-it offer per project.
2. **Given** an installed ops script differs from the repo copy, **When** the drift check runs, **Then** an alert names the script.

### User Story 6 - A repo joins auto-merge only with CI (Priority: P1)

**Acceptance Scenarios**:

1. **Given** a repo with no PR-triggered CI and no `ci-ok` job, **When** it is onboarded, **Then** it stays out of auto-merge and uses the bash fallback.
2. **Given** a repo with `ci-ok`, **When** onboarding checks pass, **Then** auto-merge and branch protection are enabled.

## Requirements

### Functional Requirements

- **R1**: jdelegate MUST refuse a new build worker for project P when P has >= N open non-draft PRs waiting on review or auto-merge (N = 3, Q2 answered).
- **R2**: Merging is done by GitHub auto-merge (`gh pr merge --auto --squash`), gated by the required check `ci-ok` and the pr-review verdict. Implementers open the PR, arm auto-merge on exit only when `pr-review` is already PASS/required (otherwise `bin/pr-review` queues `--auto --squash` when the verdict passes), and exit. Ticket states: building -> ready -> merged -> deploy-offered -> deployed, derived from PR state. A small bash fallback (FIFO tickets via gate-run, `-merge` locks capped at 90m, dev-stack PR #22) remains only for repos without CI.
- **R2a**: Trivial conflicts (lockfiles, lang/*.json, generated files) get one Grok 4.7 call via server-agent.sh, then CI re-runs. A code conflict or red `ci-ok` returns the PR to the SAME implementer (`jdelegate --resume`).
- **R3**: PR size <= ~400 changed lines excluding lockfiles/generated. A PR older than 48h without progress returns to its implementer or is closed with tasks reopened in the spec.
- **R4**: Every block has an owner and timeout. verdict-block -> one fix round by the same implementer within 1h (max 1 review + 1 fix round), else close and reopen tasks. The pr-review G3 exhaustion notice triggers the close path.
- **R5**: Tests run on sharded GitHub Actions, not on the project server. At merge, scoped tests for touched files run on the PR; the full suite runs every 5 merges and nightly (Q1 approved, replaces the owner rule "full gate after each merge"). Pest --parallel. The 8-CPU MediaContabo upgrade is dropped unless CI proves insufficient.
- **R6**: One tested deploy path per project in the Tokyo registry (host, user, command), proven by a dry run. One batched Deploy-it offer per day after merges.
- **R7**: Ops scripts (gate-run, gate-status, server-health, merge scripts) are installed only from dev-stack by an install script; a drift check alerts when an installed copy differs.
- **R8**: Incidents auto-resolve (done). Test/smoke runs are tagged and excluded from agent failures. Anything stale >48h becomes one daily decide-or-close line.
- **R9**: Every project repo gets PR-triggered CI with a `ci-ok` job before it joins auto-merge. crmAi and lab_chemical had no CI runs on 2026-10-30 pushes. Branch protection on main (require `ci-ok`, admins exempt) follows once CI is green.

### Key Entities

- **Ticket**: record per PR with project, branch, implementer session id, state, timestamps.
- **ci-ok**: single required check that aggregates all CI shards.
- **Deploy registry entry**: host, user, command, last dry-run date, per project.

## Owner decisions (2026-10-30)

- **Q1**: scoped tests at merge approved; tests move to GitHub Actions; 8-CPU upgrade dropped unless CI proves insufficient.
- **Q2**: N = 3.
- **Q3**: mediatgb first, then crmai and transport-tms.

## Done when

User-flow matrix. Each row is tested on a fixture repo with CI unless noted.

| # | Flow | Expected end state | Covers |
|---|------|--------------------|--------|
| F1 | Implementer opens PR, arms auto-merge, exits -> green ci-ok + pass verdict -> merged -> deploy offer | No worker alive while waiting; squash merge; one deploy offer after merges | R2 |
| F2 | Red ci-ok | PR not merged; back to same implementer via --resume | R2a |
| F3 | Trivial conflict (lockfile or lang json) | One Grok call, CI re-runs green, auto-merged | R2a |
| F4 | Code conflict | Returned to same implementer | R2a |
| F5 | N=3 PRs waiting on auto-merge, new build requested | jdelegate refuses with the count | R1 |
| F6 | PR over ~400 lines | Flagged at open, returned to split | R3 |
| F7 | Stale PR 48h | Returned to implementer or closed, tasks reopened | R3, R4 |
| F8 | verdict-block | One fix round within 1h, else closed, tasks reopened | R4 |
| F9 | pr-review G3 exhaustion notice | PR closed, tasks reopened | R4 |
| F10 | PR touching few files / 5th merge / nightly | Scoped tests on PR; full suite on 5th merge and nightly | R5 |
| F11 | Deploy dry run per project | Registry entry passes dry run as correct user on correct host | R6 |
| F12 | Installed script differs from repo | Drift alert names script; install script clears it | R7 |
| F13 | Test run (tabjob, k137, tojob style) | Tagged, absent from agent failure counts | R8 |
| F14 | Item stale >48h | One line in the daily decide-or-close digest | R8 |
| F15 | Repo without ci-ok onboarded | Stays on bash fallback; joins auto-merge after CI green | R9 |
| F16 | Repo without CI (fallback) | FIFO tickets via gate-run, 90m lock cap | R2 |

## Success Criteria

- **SC-001**: Median time from PR open to merge < 1h with green CI at default N.
- **SC-002**: Open PRs waiting on auto-merge per project never exceed the R1 limit N when a new build worker is started.
- **SC-003**: Open PRs blocked by the review bot > 48h: 0 after the first sweep.
- **SC-004**: Zero Tokyo deploy runs fail for user or host mismatch.
- **SC-005**: Zero jdelegate gate-waits poll the wrong host.
