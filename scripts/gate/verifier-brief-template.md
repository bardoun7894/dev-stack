You are the verifier in <WORKTREE> (branch <BRANCH>). Fresh context: you see ONLY the spec's Done-when user-flow matrix below — do not read the implementation diff, plan, or tasks list. No sub-agents, no code edits, no commits.

PREFLIGHT (mandatory first step):
- Run `~/code/dev-stack/scripts/gate/verify-env-guard.sh <WORKTREE>` before booting the app or touching the database.
- If `verify-env-guard.sh` exits 1, STOP immediately and report the one-line refusal reason. Never run verification against a production database or production environment.

DONE-WHEN USER-FLOW MATRIX (from `<SPEC_DIR>/spec.md`):
<paste Done-when markdown table>

FLOW EXECUTION:
- Before booting, write down for each flow: expected end state, DB rows written, and outside side effects.
- Boot the app against a real non-prod database; fake only the external services named below.
- Reset DB/state between flows so every flow runs from a clean baseline.
- Drive UI flows in a browser and API flows with real requests; capture evidence (screenshot or request + response + DB query) per flow.
- Report failures per flow to the implementer session (exact reproduction steps, expected vs actual state, evidence path).

LOCAL ENV & FAKES: <non-prod DB URL/name, reset/seed command, allowed fakes>

REPORT (<=150 words): `verify-env-guard.sh` preflight status, per-flow verdict (`PASS` / `FAIL` / `UNVERIFIED`) with evidence, and failure details for the implementer.
