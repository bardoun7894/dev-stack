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
  for 11 h; a full rerun the watcher made blocks only until GitHub shows a higher attempt number than before the rerun, not
  until it completes; no clock comparison):
  put back exactly the saved values (a value that was absent is deleted again). If `CI_RUNS_ON` no longer equals what
  the watcher set, someone changed it on purpose: drop the state, touch nothing. `CI_RUNS_ON` is never deleted when it
  had a value (the mediatgb workflow falls back to GitHub-hosted runners without it).
- D6 Reset time parse: "start again at HH:MM UTC" -> the next such time after the job's `queuedAt`; no match -> now + 60 min.
- D7 `--dry-run` prints the actions and changes nothing (no gh writes, no state write).
- D8 Move stranded runs back (2026-11-14, owner OK): runs queued while CI pointed at the fallback keep its vars, so
  after a restore they still wait on the laptop (11-14: 36 runs, ~18 h each, boat idle). Every tick, for each repo in
  boat's job list that has `CI_FALLBACK_RUNS_ON` and is not on it (not in fallback state):
  - room = (60 - 15 kept for new pushes - boat starts in the last hour, counted from `jobs[].runStartedAt`, - the
    starts of moved runs not yet started on boat) divided by the starts one run of the repo takes (most distinct
    `jobName`s in one of its boat runs; 13 when unknown).
  - Candidates: queued runs that are the newest run of their branch, oldest first, with no job started on the
    fallback (a finished preflight or a skipped job does not count) and a waiting job on the fallback labels.
  - Up to room of them get `force-cancel` (a plain cancel leaves the `always()` ci-ok job queued for a laptop runner).
  - Later ticks: once the run shows `completed`, one full `gh run rerun` (boat's vars), unless a newer run on the
    branch replaced it. A cancel that has not landed after 30 min is dropped. A rerun run counts against the room
    until boat shows one of its jobs started (or 30 min). At most 20 job lists are read per repo per tick.

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
- T8 Restore with 20 boat starts used and 9 starts per run: oldest unstarted runs moved, newest per branch only, at
  most 2 (25 starts of room); started runs and runs over the room stay; full rerun only after the cancel lands; a run
  replaced by a newer push is not rerun; 40 starts used moves nothing; a cancel that never lands is dropped after
  30 min; `--dry-run` moves nothing; runs stranded while CI is already on boat (no fallback state) move too; moved
  runs not yet started on boat use the room; nothing moves while the repo is on the fallback. T3 also: a rerun
  blocks the restore until its attempt number went up, not until it ends.

### User-flow matrix (verifier, live)
| Flow | Steps | Pass |
|---|---|---|
| F1 Boat full | Next real plan-limit pause on mediatgb | within 4 min the vars point to the laptop and the run is rerun there; log line shows it |
| F2 Room again | 15 min after the reset, no active laptop runs | `CI_RUNS_ON` back to `"boat"`, `CI_CONTAINER` gone |
| F3 Stranded runs | Restore while runs wait unstarted on the laptop | log shows "moving it to boat" then "rerun ... in full on boat"; those runs' jobs carry the `boat` label |

## Review (Opus, one round) and fixes
- P1 deleting an absent `CI_CONTAINER` failed (404) and lost the state: `set_var` skips writes that change nothing.
- P1 a crash after the switch lost the saved values: state is written before the var writes; `gh_cli` turns
  timeouts and missing gh into rc 1; bad JSON from gh is handled.
- P2 `rerun --failed` skipped when the run was already rerun after the pause; unreadable runs are dropped from
  pending/later so they never block the way back. Cron runs under `flock -n`.

## Review of D8 (Opus medium, one round, 2026-11-14) and fixes
- P1 a rerun read `completed` in its own tick and unblocked the restore: a run the watcher reran unblocks only on a
  higher attempt number (or when deleted); an unreadable baseline waits for completion.
- Fixed: repos the watcher moved are remembered (`fallback_repos`), so one with no jobs left in `/ci` is still
  checked; pending moves carry their own start count; the room is checked before any gh call; step 2 reads each run once.
- Not changed: vars fixed per attempt is evidenced in #47 (Pest jobs created 40 min later ran on the attempt's
  runner); `/ci` lists completed jobs (163 of 200 on 11-14); save-at-end of tick is the existing pattern; the
  check-then-cancel race is sub-second (P2).
