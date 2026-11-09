# Spec 002 — jdelegate: no test jobs in the live registry, no repeat launches into a dead provider

**Branch**: `002-jdelegate-health` · **Requested**: 2026-11-08 by owner ("fix them", after factory specs 007-009 shipped)

## Evidence (live registry /root/.factory-control/registry.db, 2026-11-08)
- E1 1,602 jobs are `queued` with no run at all, all older than 2 days. 1,371 of them have project `repo` and arrive in
  bursts of 70-150 per minute (2026-11-06T15:3x, 19:4x, 2026-11-03T07:0x, ...). Owners: jdelegate 1,179, reviewer 231,
  debugger 137, designer 14, big 14, researcher 11. These are jdelegate test runs: `regOn()` (`bin/jdelegate:891`) is
  true unless `FACTORY_BIN` is set, and any test or run without it calls `factory submit` on MyContabo over ssh.
- E2 774 of 1,875 Claude sessions (41%) since 2026-10-25 are error-only ("API Error: 503 auth_unavailable" from the
  cliproxy at :8317, "You've hit your weekly limit"). jdelegate marks a provider exhausted only for agy quota and the codex
  "usage limit" text (`bin/jdelegate:517-540, 1018-1040`), so the next run routes into the same dead provider.

## Design
- D1 Registration is off for throwaway work: `regOn()` is false when `opt.cwd` resolves inside `os.tmpdir()` (or `/tmp`,
  `/private/tmp`), when `--dry-run` is given, or when `JDELEGATE_REG=0`. Everything else unchanged.
- D2 Every test entry point in `tests/` (jdelegate.test.mjs helpers, test_jdelegate_*.py, any spawn of bin/jdelegate) runs
  with registration off or a fake `JDELEGATE_REG_SSH`; add a test-suite guard that fails if a test would ssh to a real host
  (fake `ssh` first on PATH that records and exits 1 for any host other than the fake).
- D3 Error-only start: when a claude worker's output (out.log) has only API-error turns in its first 3 assistant turns
  (`API Error: 5xx`, `auth_unavailable`, `hit your weekly limit`, `hit your usage limit`, model `<synthetic>`), jdelegate
  writes the provider into `exhausted.json` (same file and shape the router already reads) for 30 min (weekly-limit text
  with a parseable reset time: until that time), ends the run with reason `api errors`, and retries ONCE on the next
  candidate of the same chain. A second error-only start does not retry.
- D4 The run's `frun finish` reason is `api errors` for D3, so GodHome and `factory-measure builds` can count them.

## Out of scope
server-agent.sh (not in git; factory launches reach it through pqrun, gated by software-factory spec 008), the cliproxy
itself, cleaning the existing 1,602 rows (software-factory spec 010 + one reconcile).

## Done when
- `node --test tests/jdelegate.test.mjs` and `python3 -m pytest tests/test_jdelegate_register.py tests/test_jdelegate_p6.py`
  green, with new tests: T1 cwd in tmpdir -> no ssh call; T2 `--dry-run` -> no ssh call; T3 `JDELEGATE_REG=0` -> none;
  T4 real cwd -> submit still called (fake ssh); T5 the suite guard fails a test that would reach a real host;
  T6 error-only claude output -> provider in exhausted.json + one retry on the next candidate; T7 second error-only start
  -> no second retry; T8 a normal worker with one transient API error then real turns -> no retry.
- After merge, a full test run (gate queue) adds zero rows to the live registry: count `jobs` before and after.
- User-flow matrix:

| Flow | Start | Steps | Expected | Rows | Side effects |
|---|---|---|---|---|---|
| F1 | live registry count N | run the jdelegate test suite | registry count still N | none | none |
| F2 | fake claude printing 3 `API Error: 503 auth_unavailable` turns | `jdelegate --cwd <repo> "<brief>"` | first run ends `api errors`, provider in exhausted.json, second run on next candidate | 2 runs (fake reg) | exhausted.json entry |
| F3 | F2 state | run again within 30 min | router skips the exhausted provider from the start | 1 run | none |

## Result (implementer, 2026-11-09)
- F1: live registry `jobs` count 3940 before and 3942 after the one full scoped run. The two new rows are project `review`, owner `reviewer`,
  created 00:16:52 and 00:17:11Z while the run was going: a real concurrent review job from another session, not a jdelegate test (tests use project `repo`, and the ssh guard logged no real host).
- T1-T8 and the D2 guard are in tests/jdelegate.test.mjs (T1-T3 also in test_jdelegate_register.py); tests/fake-ssh-guard.sh is the guard ssh.
- Second scoped run was spent: T4/T7 stub fix (stub must drain stdin, else exit 141) and T6/T7 (no `--harness`, so the retry may leave claude) were fixed after it and are not re-run.
