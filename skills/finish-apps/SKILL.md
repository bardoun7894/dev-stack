---
name: finish-apps
description: Portfolio orchestrator that finds the apps worked on this week (Mac + MyContabo), has Jev score how finished each is and pick the next action, then drives readiness-audit, market-swot and kb-dev workers per project with one hard owner-approval stop before any implementation. Triggers on "which apps are not finished", "finish the apps", "complete the apps", "what's active this week", "check specs across projects", "/finish-apps", and Arabic "شو التطبيقات يلي ما خلصت", "كمل التطبيقات".
allowed-tools: Bash Read Write Glob Grep Skill
---

# finish-apps

Composes existing skills; it does not redo their work. Scripts live in `skills/finish-apps/scripts/`
(zero AI). Jev does all scoring and ranking; the LLM never sorts. Customer projects are listed in
`config/customers.txt` (sanad_app, up): report-only in every phase, no spec edits, no implementation.

## Phases

| # | Phase | How |
|---|-------|-----|
| 0 | Active projects | `bash scripts/active.sh [--days 7] [--host mac\|server\|all] > /tmp/fa-active.json`. Show a table P1..Pn (name, host, commits, last commit, specs missing plan/tasks, open tasks, customer). Keep the codes for the whole run. Server down = warning, Mac results only. |
| 1 | Triage | `bash scripts/triage.sh /tmp/fa-active.json > /tmp/fa-triage.json`. Adds `completeness` (0-4) and `next_action` per project; `needs-llm` means Jev was unsure, so you decide that one by reading the project (never treat it as pass). |
| 1b | Recommend | `bash scripts/recommend.sh /tmp/fa-triage.json [--top 3] > /tmp/fa-rec.json`. Per project R1..R3 (title, kind, why, evidence, size, Jev impact; one LLM call per project, Jev ranks). The owner card/app shows them with buttons [Write spec R1] [R2] [R3] [Skip]; a tap writes ONLY that spec via readiness-audit phase 4 / kb-spec pre + speckit.specify. Implementation still needs the phase-3 approval. Customer projects: `report_only`, shown but not written. |
| 2 | Per-project work | By `next_action`: write-specs, fix-defects, verdict: run `readiness-audit <project> --defects` (phases 0-4; add `--report-only` when `report_only`). research-features: `market-swot project <path>`, then readiness-audit. implement-open-tasks: skip to phase 3. At most 3 projects in parallel, different projects only; website projects run on MyContabo per `where-to-work`. |
| 3 | HARD STOP | Write `~/projects/_finish-apps/<date>/FINISH-APPS-<date>.md`: per project completeness, next action, the G codes from readiness-audit, specs written, what would be implemented. Ask the owner which to implement. Nothing is implemented before an explicit yes. Customer projects stay report-only. |
| 4 | Implement | Only approved specs. Per spec: `jev route "<spec title + scope>"` for the tier, then `jdelegate --no-auto-mcp --no-auto-skill --no-auto-role --cwd <worktree> --name <label> "<brief>"` with the brief from `scripts/gate/brief-template.md`. Run `scripts/gate/overlap.sh <repo-root> <branches...>` before running branches in parallel. Gates run through `gaterun.sh` / `gate.sh`; wait with `monitor.sh` once (background). The orchestrator never polls. |
| 5 | Verdict | Re-run `active.sh` and `triage.sh`, show completeness before/after per project. For each project that reached production-ready, ask the CLAUDE.md "Deploy it?" question (tokyo-deploy). Never deploy unasked. |

## Rules

- Phases 0 and 1 are cheap and deterministic: run them every time, do not summarise from memory.
- readiness-audit owns inventory (`skills/readiness-audit/scripts/inventory.sh`), defects and the spec edits;
  market-swot owns competitor and feature research. Quote their codes (G, F, S/W/O/T), do not restate their analysis.
- Never commit on main. Each implementation runs in its own git worktree and branch.

## Token budget

- One pass per worker: one brief, one report. No re-briefing a worker that is mid-task.
- At most 3 workers in parallel, on different projects or non-overlapping files (`overlap.sh`).
- One review round and one fix round per branch, then stop and report.
- Scoped tests only via `testcap.sh` (2 per branch); the full gate runs from `.gate.conf` in bash.
- Loops, queues and waiting live in bash (`gaterun.sh`, `monitor.sh`); the AI wakes on PASS, FAIL or STALL.
- Jev decides labels and scores (about $0.00002 a call); do not spend LLM tokens ranking or classifying.

## Files

- `scripts/active.sh`, `scripts/triage.sh`, `scripts/recommend.sh`, `config/customers.txt`
- Tests: `tests/finish-apps/active_test.sh`, `tests/finish-apps/triage_test.sh`, `tests/finish-apps/recommend_test.sh`
- Mac snapshot: `scripts/push-mac-snapshot.sh` pushes the Mac scan to the server (`/root/.tokyo/finish-apps/mac-latest.json`); server-mode `active.sh` reads it (flagged `snapshot: true`) when `ssh mac` fails and it is under 24h old.
- Installer: `bash scripts/install-mac-push.sh` loads the launchd agent (every 2h) from `launchd/dev.mbardouni.finish-apps-push.plist`.
- Env: `FINISH_APPS_MAC_ROOTS`, `FINISH_APPS_SERVER_ROOTS`, `FINISH_APPS_SSH_HOST`, `FINISH_APPS_SELF`, `FINISH_APPS_MAC_ROOTS_REMOTE`, `JEV_BIN`, `FINISH_APPS_LLM`
