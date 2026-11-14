# Spec 003: boat first, other machines when boat is full

**Branch**: `003-boat-fallback` · **Requested**: 2026-11-11 by owner
("use boat ci always if there is place then the other devices.")

## Evidence (2026-11-11)
- The boat plan includes 60 sandbox starts per rolling hour. Each CI job is one start; one MEDIA TGB run is 13 jobs.
- When the starts run out, boat marks the job `paused` in `GET /api/v1/ci` (`jobs[].state == "paused"`,
  `shortReason` "Paused by plan limit...", `reason` names the reset: "New ones can start again at 07:40 UTC.") and
  GitHub fails the run. Run 42976859099 had 6 paused jobs.
- A full `gh run rerun <id>` (not `--failed`) re-reads repo variables: with mediatgb `CI_RUNS_ON` set to the laptop
  runners and `CI_CONTAINER` set, attempt 3 of that run went to cachy-ci-1..3.

## Design
- D1 `boat.py ci fallback [--dry-run]` (module `boat_fallback.py`, stdlib, gh via subprocess), run every 2 min by cron
  on MyContabo. State in `~/.local/state/boat-fallback.json`, one log line per action in `boat-fallback.log`.
- D2 Paused jobs are grouped by repo and run. A job id is handled once.
- D3 Repo with a fallback (repo var `CI_FALLBACK_RUNS_ON`, optional `CI_FALLBACK_CONTAINER`):
  - First paused job: save the current `CI_RUNS_ON` / `CI_CONTAINER` in the state file, set `CI_RUNS_ON` to the
    fallback and `CI_CONTAINER` to the fallback container (deleted when there is none). `until` = reset time + 15 min.
  - Each paused run, once GitHub shows it `completed`: one full `gh run rerun <id>` (never `--failed`: the shard count
    comes from the vars).
  - More paused jobs while in fallback push `until` out.
- D4 Repo without a fallback: after the reset time + 2 min, `gh run rerun <id> --failed` once per run.
- D5 Restore after `until` (2026-11-14: runs still queued or running on the fallback no longer block; GitHub fixes vars
  per run attempt, so they finish there with their own shard count, and a steady laptop queue had kept CI off boat
  for 11 h):
  put back exactly the saved values (a value that was absent is deleted again). If `CI_RUNS_ON` no longer equals what
  the watcher set, someone changed it on purpose: drop the state, touch nothing. `CI_RUNS_ON` is never deleted when it
  had a value (the mediatgb workflow falls back to GitHub-hosted runners without it).
- D6 Reset time parse: "start again at HH:MM UTC" -> the next such time after the job's `queuedAt`; no match -> now + 60 min.
- D7 `--dry-run` prints the actions and changes nothing (no gh writes, no state write).

## Out of scope
- Counting starts to switch before boat is full (`/usage` is 403 for this key; sandboxes also use starts).
- Registering laptop runners for repos other than mediatgb; local `gate-run` routing (D2 of the CI split, later).

## Done when
- T1 Paused job on a repo with `CI_FALLBACK_RUNS_ON`: vars set to the fallback, state saved, run rerun in full once
  the run is completed; not rerun while it is in progress; a second tick does nothing new.
- T2 Repo without fallback: no var writes; `rerun --failed` only after reset + 2 min, once.
- T3 Restore after `until`: saved values put back (absent -> deleted); before `until`: no restore; active runs on
  the fallback do not block it.
- T4 `CI_RUNS_ON` changed by someone else: state dropped, no var write.
- T5 Reset parse: "07:40 UTC" with queuedAt 07:10 -> 07:40 same day; queuedAt 23:50 and "00:30 UTC" -> next day.
- T6 `--dry-run` makes no gh write and no state write.
- T7 Existing `test_boat.py` stays green.

### User-flow matrix (verifier, live)
| Flow | Steps | Pass |
|---|---|---|
| F1 Boat full | Next real plan-limit pause on mediatgb | within 4 min the vars point to the laptop and the run is rerun there; log line shows it |
| F2 Room again | 15 min after the reset, no active laptop runs | `CI_RUNS_ON` back to `"boat"`, `CI_CONTAINER` gone |

## Review (Opus, one round) and fixes
- P1 deleting an absent `CI_CONTAINER` failed (404) and lost the state: `set_var` skips writes that change nothing.
- P1 a crash after the switch lost the saved values: state is written before the var writes; `gh_cli` turns
  timeouts and missing gh into rc 1; bad JSON from gh is handled.
- P2 `rerun --failed` skipped when the run was already rerun after the pause; unreadable runs are dropped from
  pending/later so they never block the way back. Cron runs under `flock -n`.
