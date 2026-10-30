# Feature Specification: factory-flow

**Feature Branch**: `spec-002-factory-flow`  
**PR**: TBD  
**Merged**: TBD  
**Created**: 2026-10-30  
**Status**: Draft  
**Input**: The agent software factory (jdelegate workers -> PR review bot -> merge via gate-run -> deploy via tokyo-deploy) piles up because work enters faster than the test gate finishes it. Add a WIP limit tied to gate capacity and a code-driven merge-queue service. Spec only, no code in this PR.

## User Scenarios & Testing

### User Story 1 - Implementer drops a ticket and exits (Priority: P1)

An implementer worker finishes a branch, drops a ticket into the project queue and exits. A bash/systemd merge-queue service on the project server merges tickets FIFO through gate-run. No LLM runs while waiting.

**Why this priority**: removes the pile-up and the workers that poll for hours.

**Independent Test**: drop three tickets on a fixture project; they merge in drop order and no jdelegate process is alive while they wait.

**Acceptance Scenarios**:

1. **Given** an empty queue, **When** an implementer drops a ticket, **Then** state goes building -> ready -> merging -> merged -> deploy-offered.
2. **Given** three ready tickets, **When** the service runs, **Then** merge order equals ticket order.

### User Story 2 - Queue full stops new build work (Priority: P1)

**Why this priority**: work must not enter faster than the gate finishes it.

**Independent Test**: fill the fixture queue to N; `jdelegate` for a build role on that project exits non-zero with a reason.

**Acceptance Scenarios**:

1. **Given** project P has >= N ready-to-merge tickets, **When** a build worker is requested for P, **Then** jdelegate refuses and names the queue length.
2. **Given** the queue drops below N, **When** the request is repeated, **Then** it is accepted.

### User Story 3 - Red gate or code conflict returns to the same implementer (Priority: P1)

**Independent Test**: fixture ticket with a failing test; the service marks it returned, resumes the same worker, and merges the next ticket.

**Acceptance Scenarios**:

1. **Given** a red gate, **When** the service sees it, **Then** the ticket goes back to the same implementer via `jdelegate --resume` and the queue moves on.
2. **Given** a trivial conflict (lockfile, lang/*.json, generated file), **When** detected, **Then** one Grok 4.7 call via server-agent.sh resolves it and the gate re-runs.

### User Story 4 - Stale work and blocks have owners and timeouts (Priority: P2)

**Acceptance Scenarios**:

1. **Given** a PR older than 48h without progress, **When** the daily sweep runs, **Then** it returns to its implementer or is closed with its tasks reopened in the spec.
2. **Given** verdict-block, **When** the review bot posts it, **Then** the same implementer gets one fix round within 1h, else the PR is closed and tasks reopened.

### User Story 5 - Deploy and ops hygiene (Priority: P2)

**Acceptance Scenarios**:

1. **Given** merges happened today, **When** the daily offer runs, **Then** the owner gets one batched Deploy-it offer per project.
2. **Given** an installed ops script differs from the repo copy, **When** the drift check runs, **Then** an alert names the script.

## Requirements

### Functional Requirements

- **R1**: jdelegate MUST refuse a new build worker for project P when P ready-to-merge queue has >= N tickets (N default 3, Q2).
- **R2**: Tickets MUST follow building -> ready -> merging -> merged -> deploy-offered -> deployed, moved by a bash/systemd merge-queue service on the project server. No LLM while waiting. Implementers drop a ticket and exit. Merge order is FIFO via gate-run tickets.
- **R2a**: Trivial conflicts (lockfiles, lang/*.json, generated files) get one Grok 4.7 call via server-agent.sh, then re-gate. A code conflict or red gate returns to the SAME implementer (`jdelegate --resume`) and the queue moves on.
- **R3**: PR size <= ~400 changed lines excluding lockfiles/generated. A PR older than 48h without progress returns to its implementer or is closed with tasks reopened in the spec.
- **R4**: Every block has an owner and timeout. verdict-block -> one fix round by the same implementer within 1h (max 1 review + 1 fix round), else close and reopen tasks.
- **R5**: At merge run scoped tests for touched files; full suite every 5 merges and nightly (Q1; changes owner rule "full gate after each merge"); Pest --parallel; optional MediaContabo upgrade to 8 CPU (Q1, owner purchase).
- **R6**: One tested deploy path per project in the Tokyo registry (host, user, command), proven by a dry run. One batched Deploy-it offer per day after merges.
- **R7**: Ops scripts (gate-run, gate-status, server-health, merge scripts) are installed only from dev-stack by an install script; a drift check alerts when an installed copy differs.
- **R8**: Incidents auto-resolve (done). Test/smoke runs are tagged and excluded from agent failures. Anything stale >48h becomes one daily decide-or-close line.

### Key Entities

- **Ticket**: file per branch with project, branch, implementer session id, state, timestamps.
- **Merge-queue service**: systemd unit plus bash loop per project server.
- **Deploy registry entry**: host, user, command, last dry-run date, per project.

## Open Questions for the Owner

- **Q1**: Scoped tests at merge vs 8-CPU upgrade vs both. Default: both. Changes the owner rule "full gate after each merge".
- **Q2**: Queue limit N. Default 3.
- **Q3**: Which projects get the service first. Default mediatgb on MediaContabo, then crmai and transport-tms on MyContabo.

## Done when

User-flow matrix. Each row is a script-level test on a fixture project, run on the project server.

| # | Flow | Expected end state | Covers |
|---|------|--------------------|--------|
| F1 | Implementer finishes -> ticket queued -> merged FIFO -> deploy offer | Implementer exited; merges in ticket order; one deploy offer after merges | R2 |
| F2 | Red gate | Ticket back to same implementer via --resume; next ticket merges | R2, R2a |
| F3 | Trivial conflict (lockfile or lang json) | One Grok call, re-gate green, merged | R2a |
| F4 | Code conflict | Returned to same implementer, queue moves on | R2a |
| F5 | Queue has N tickets, new build requested | jdelegate refuses with queue length | R1 |
| F6 | PR over ~400 lines | Flagged at ticket drop, returned to split | R3 |
| F7 | Stale PR 48h | Returned to implementer or closed, tasks reopened | R3, R4 |
| F8 | verdict-block | One fix round within 1h, else closed, tasks reopened | R4 |
| F9 | 5th merge / nightly | Full suite runs; other merges run scoped tests only | R5 |
| F10 | Deploy dry run per project | Registry entry passes dry run as correct user on correct host | R6 |
| F11 | Installed script differs from repo | Drift alert names script; install script clears it | R7 |
| F12 | Test run (tabjob, k137, tojob style) | Tagged, absent from agent failure counts | R8 |
| F13 | Item stale >48h | Appears as one line in the daily decide-or-close digest | R8 |

## Success Criteria

- **SC-001**: Oldest ready ticket waits < 2h at the default N.
- **SC-002**: Live build workers per project never exceed the jdelegate limit.
- **SC-003**: Open PRs blocked by the review bot > 48h: 0 after the first sweep.
- **SC-004**: Zero Tokyo deploy runs fail for user or host mismatch.
