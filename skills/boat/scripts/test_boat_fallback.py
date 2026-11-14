import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boat_fallback as bf  # noqa: E402

REPO = "o/mtgb"
OTHER = "o/small"
FALLBACK = '["self-hosted","cachy"]'
CONTAINER = '{"image":"localhost:5000/ci:2"}'
REASON = ("You used all 60 sandbox starts included in the last hour.\n"
          "Your running sandboxes keep running. New ones can start again at 07:40 UTC.\nThen try again.")


def t(hhmm, day=11):
    h, m = hhmm.split(":")
    return datetime(2026, 11, day, int(h), int(m), tzinfo=timezone.utc)


def job(jid, repo=REPO, run="100", state="paused", queued="2026-11-11T07:10:00Z", reason=REASON):
    return {"id": jid, "repo": repo, "runId": run, "state": state, "queuedAt": queued, "reason": reason,
            "shortReason": "Paused by plan limit. Re-run it to continue."}


class FakeGh:
    """Fake gh: repo vars, run statuses, records writes."""

    def __init__(self):
        self.vars = {REPO: {"CI_RUNS_ON": '"boat"', "CI_FALLBACK_RUNS_ON": FALLBACK,
                            "CI_FALLBACK_CONTAINER": CONTAINER},
                     OTHER: {}}
        self.runs = {}           # (repo, run) -> status
        self.started = {}        # (repo, run) -> latest attempt start
        self.active_since = {}   # repo -> list of runs created after a time that are not completed
        self.writes = []

    def __call__(self, args):
        if args[:2] == ["variable", "list"]:
            repo = args[args.index("-R") + 1]
            import json
            return 0, json.dumps([{"name": k, "value": v} for k, v in self.vars.get(repo, {}).items()])
        if args[:2] == ["variable", "set"]:
            repo = args[args.index("-R") + 1]
            self.vars[repo][args[2]] = args[args.index("--body") + 1]
            self.writes.append(("set", repo, args[2]))
            return 0, ""
        if args[:2] == ["variable", "delete"]:
            repo = args[args.index("-R") + 1]
            if args[2] not in self.vars[repo]:
                return 1, "HTTP 404"  # like real gh
            self.vars[repo].pop(args[2], None)
            self.writes.append(("delete", repo, args[2]))
            return 0, ""
        if args[:2] == ["run", "view"]:
            import json
            repo = args[args.index("-R") + 1]
            return 0, json.dumps({"status": self.runs.get((repo, args[2]), "completed"),
                                  "startedAt": self.started.get((repo, args[2]), "2026-11-11T07:04:00Z")})
        if args[:2] == ["run", "rerun"]:
            repo = args[args.index("-R") + 1]
            self.writes.append(("rerun", repo, args[2], "--failed" in args))
            return 0, ""
        if args[:2] == ["run", "list"]:
            import json
            repo = args[args.index("-R") + 1]
            return 0, json.dumps(self.active_since.get(repo, []))
        raise AssertionError("unexpected gh call %r" % (args,))


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = Path(self.tmp.name) / "state.json"
        self.log = Path(self.tmp.name) / "log"
        self.gh = FakeGh()

    def tearDown(self):
        self.tmp.cleanup()

    def tick(self, jobs, now, dry=False):
        return bf.tick(jobs, now=now, gh=self.gh, state_path=self.state, log_path=self.log, dry_run=dry)


class T1Fallback(Base):
    def test_switch_and_full_rerun_once(self):
        self.gh.runs[(REPO, "100")] = "in_progress"
        self.tick([job("j1"), job("j2")], t("07:12"))
        self.assertEqual(self.gh.vars[REPO]["CI_RUNS_ON"], FALLBACK)
        self.assertEqual(self.gh.vars[REPO]["CI_CONTAINER"], CONTAINER)
        self.assertFalse(any(w[0] == "rerun" for w in self.gh.writes), "no rerun while in progress")
        st = bf.load_state(self.state)
        self.assertEqual(st["repos"][REPO]["saved"], {"CI_RUNS_ON": '"boat"', "CI_CONTAINER": None})
        self.gh.runs[(REPO, "100")] = "completed"
        self.tick([job("j1"), job("j2")], t("07:14"))
        reruns = [w for w in self.gh.writes if w[0] == "rerun"]
        self.assertEqual(reruns, [("rerun", REPO, "100", False)])
        n = len(self.gh.writes)
        self.tick([job("j1"), job("j2")], t("07:16"))
        self.assertEqual(len(self.gh.writes), n, "second tick does nothing new")

    def test_more_pauses_push_until_out(self):
        self.tick([job("j1")], t("07:12"))
        later = REASON.replace("07:40", "08:20")
        self.tick([job("j1"), job("j9", run="101", queued="2026-11-11T07:50:00Z", reason=later)], t("07:52"))
        st = bf.load_state(self.state)
        self.assertEqual(st["repos"][REPO]["until"], "2026-11-11T08:35:00+00:00")


class T2NoFallback(Base):
    def test_rerun_failed_after_reset_once(self):
        j = job("k1", repo=OTHER, run="200")
        self.tick([j], t("07:30"))
        self.assertEqual(self.gh.writes, [])
        self.tick([j], t("07:43"))
        self.assertEqual(self.gh.writes, [("rerun", OTHER, "200", True)])
        self.tick([j], t("07:45"))
        self.assertEqual(len(self.gh.writes), 1)


class T3Restore(Base):
    def test_restore_after_until(self):
        self.tick([job("j1")], t("07:12"))
        self.tick([job("j1")], t("07:54"))
        self.assertEqual(self.gh.vars[REPO]["CI_RUNS_ON"], FALLBACK, "before until: no restore")
        self.tick([job("j1")], t("07:56"))
        self.assertEqual(self.gh.vars[REPO]["CI_RUNS_ON"], '"boat"')
        self.assertNotIn("CI_CONTAINER", self.gh.vars[REPO])
        self.assertNotIn(REPO, bf.load_state(self.state)["repos"])

    def test_rerun_in_flight_blocks_restore(self):
        self.tick([job("j1")], t("07:12"))  # run 100 completed -> rerun in full
        self.gh.runs[(REPO, "100")] = "in_progress"
        self.tick([job("j1")], t("07:58"))
        self.assertEqual(self.gh.vars[REPO]["CI_RUNS_ON"], FALLBACK, "rerun still running: stay on fallback")
        self.gh.runs[(REPO, "100")] = "completed"
        self.tick([job("j1")], t("07:59"))
        self.assertEqual(self.gh.vars[REPO]["CI_RUNS_ON"], '"boat"')
        self.assertNotIn(REPO, bf.load_state(self.state)["repos"])

    def test_unreadable_rerun_blocks_restore(self):
        self.tick([job("j1")], t("07:12"))
        real = self.gh.__call__
        gone = lambda a: (1, "not found") if a[:3] == ["run", "view", "100"] else real(a)
        bf.tick([job("j1")], now=t("07:58"), gh=gone, state_path=self.state, log_path=self.log)
        self.assertEqual(self.gh.vars[REPO]["CI_RUNS_ON"], FALLBACK)


class T4ChangedByOthers(Base):
    def test_changed_var_drops_state(self):
        self.tick([job("j1")], t("07:12"))
        self.gh.vars[REPO]["CI_RUNS_ON"] = '"boat-large"'
        n = len(self.gh.writes)
        self.tick([job("j1")], t("07:58"))
        self.assertEqual(len(self.gh.writes), n)
        self.assertEqual(self.gh.vars[REPO]["CI_RUNS_ON"], '"boat-large"')
        self.assertNotIn(REPO, bf.load_state(self.state)["repos"])


class T5Parse(unittest.TestCase):
    def test_same_day(self):
        self.assertEqual(bf.reset_time(REASON, "2026-11-11T07:10:00Z", t("07:12")), t("07:40"))

    def test_next_day(self):
        r = REASON.replace("07:40", "00:30")
        self.assertEqual(bf.reset_time(r, "2026-11-11T23:50:00Z", t("23:52")), t("00:30", day=12))

    def test_no_match(self):
        self.assertEqual(bf.reset_time("odd", "2026-11-11T07:10:00Z", t("07:12")), t("08:12"))


class T6DryRun(Base):
    def test_no_writes(self):
        self.tick([job("j1"), job("k1", repo=OTHER, run="200")], t("07:50"), dry=True)
        self.assertEqual(self.gh.writes, [])
        self.assertFalse(self.state.exists())


class AlreadyHandled(Base):
    def test_run_rerun_after_pause_is_skipped(self):
        self.gh.started[(REPO, "100")] = "2026-11-11T07:20:00Z"
        self.tick([job("j1")], t("07:22"))
        self.assertEqual(self.gh.writes, [])
        self.assertIn("j1", bf.load_state(self.state)["handled"])

    def test_vars_already_on_fallback_are_not_owned(self):
        self.gh.vars[REPO]["CI_RUNS_ON"] = FALLBACK
        self.gh.vars[REPO]["CI_CONTAINER"] = CONTAINER
        self.tick([job("j1")], t("07:12"))
        self.assertEqual(self.gh.writes, [("rerun", REPO, "100", False)])
        self.tick([job("j1")], t("07:58"))
        self.assertEqual(self.gh.vars[REPO]["CI_RUNS_ON"], FALLBACK, "never restores values it did not set")
        self.assertNotIn(REPO, bf.load_state(self.state)["repos"])


class ReviewFixes(Base):
    def test_no_fallback_container_and_no_container_switches_cleanly(self):
        del self.gh.vars[REPO]["CI_FALLBACK_CONTAINER"]
        self.tick([job("j1")], t("07:12"))
        self.assertEqual(self.gh.vars[REPO]["CI_RUNS_ON"], FALLBACK)
        st = bf.load_state(self.state)
        self.assertEqual(st["repos"][REPO]["saved"]["CI_RUNS_ON"], '"boat"')
        self.tick([job("j1")], t("07:58"))
        self.assertEqual(self.gh.vars[REPO]["CI_RUNS_ON"], '"boat"')
        self.assertFalse(any(w[0] == "delete" for w in self.gh.writes))

    def test_crash_after_switch_keeps_saved_values(self):
        real = self.gh.__call__

        def boom(args):
            if args[:2] == ["run", "view"] and self.gh.vars[REPO]["CI_RUNS_ON"] == FALLBACK:
                raise RuntimeError("crash")
            return real(args)
        with self.assertRaises(RuntimeError):
            bf.tick([job("j1")], now=t("07:12"), gh=boom, state_path=self.state, log_path=self.log)
        self.assertEqual(bf.load_state(self.state)["repos"][REPO]["saved"]["CI_RUNS_ON"], '"boat"')
        self.tick([job("j1")], t("07:14"))
        self.tick([job("j1")], t("07:58"))
        self.assertEqual(self.gh.vars[REPO]["CI_RUNS_ON"], '"boat"')

    def test_later_skipped_when_someone_reran(self):
        j = job("k1", repo=OTHER, run="200")
        self.tick([j], t("07:30"))
        self.gh.started[(OTHER, "200")] = "2026-11-11T07:35:00Z"
        self.tick([j], t("07:43"))
        self.assertEqual(self.gh.writes, [])
        self.assertEqual(bf.load_state(self.state)["later"], {})

    def test_unreadable_pending_run_does_not_block_restore(self):
        self.gh.runs[(REPO, "100")] = "in_progress"
        self.tick([job("j1")], t("07:12"))
        real = self.gh.__call__
        gone = lambda a: (1, "not found") if a[:3] == ["run", "view", "100"] else real(a)
        bf.tick([job("j1")], now=t("07:58"), gh=gone, state_path=self.state, log_path=self.log)
        self.assertEqual(self.gh.vars[REPO]["CI_RUNS_ON"], '"boat"')


class Ignores(Base):
    def test_non_paused_jobs_ignored(self):
        self.tick([job("j1", state="success"), job("j2", state="failure")], t("07:12"))
        self.assertEqual(self.gh.writes, [])


if __name__ == "__main__":
    unittest.main()
