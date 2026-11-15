"""Boat used only for P1 runs and only within the plan: daily vs hourly reset, cap still on, P1 filter, light jobs.
Reason strings are the real ones from boat /ci on 2026-11-15."""
import json
import os
import sys
import unittest
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boat_fallback as bf  # noqa: E402
from test_boat_fallback import OTHER, REPO, Base, job, t  # noqa: E402
from test_boat_fallback_moves import boat_history, gh_job  # noqa: E402

DAILY_DATED = ("You used all 200 sandbox starts included in the last 24 hours.\nYour running sandboxes keep running. "
               "New ones can start again at Nov 15, 06:05 UTC.\nThen try again.")
DAILY = ("You used all 200 sandbox starts included in the last 24 hours.\nYour running sandboxes keep running. "
         "New ones can start again at 06:05 UTC.\nThen try again.")
HOURLY = ("You used all 60 sandbox starts included in the last hour.\nYour running sandboxes keep running. "
          "New ones can start again at 08:21 UTC.\nThen try again.")
HEAVY = ["self-hosted", "cachy", "heavy"]
LIGHT = ["self-hosted", "mtgb-light"]


def at(s):
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


class ResetTime(unittest.TestCase):
    def test_daily_with_date_is_that_time_not_one_hour(self):
        self.assertEqual(bf.reset_time(DAILY_DATED, "2026-11-14T19:00:00Z", at("2026-11-15T00:40:00")),
                         at("2026-11-15T06:05:00"))

    def test_daily_without_date_is_the_next_such_time(self):
        self.assertEqual(bf.reset_time(DAILY, "2026-11-14T23:00:00Z", at("2026-11-14T23:02:00")),
                         at("2026-11-15T06:05:00"))

    def test_hourly(self):
        self.assertEqual(bf.reset_time(HOURLY, "2026-11-15T07:30:00Z", at("2026-11-15T07:31:00")),
                         at("2026-11-15T08:21:00"))

    def test_daily_without_time_waits_a_day_not_an_hour(self):
        r = "You used all 200 sandbox starts included in the last 24 hours."
        self.assertEqual(bf.reset_time(r, "2026-11-15T01:00:00Z", at("2026-11-15T01:02:00")), at("2026-11-16T01:00:00"))

    def test_year_wrap(self):
        r = DAILY_DATED.replace("Nov 15", "Jan 1")
        self.assertEqual(bf.reset_time(r, "2026-12-31T22:00:00Z", at("2026-12-31T22:01:00")), at("2027-01-01T06:05:00"))

    def test_cap_window(self):
        self.assertEqual([bf.cap_window(x) for x in (DAILY, HOURLY, "odd")], ["day", "hour", None])


class P1Only(Base):
    """Stranded runs move to boat only when P1, only while no paused job says a cap is still on."""

    def setUp(self):
        super().setUp()
        self.gh.vars[REPO]["CI_HEAVY_RUNS_ON"] = json.dumps(HEAVY)
        rows = [("301", "feature-x", "pull_request", "08:20"), ("302", "train-c-1114", "pull_request", "08:21"),
                ("303", "main", "push", "08:22"), ("304", "main", "pull_request", "08:23"),
                ("305", "proof-2731921a0", "pull_request", "08:24")]
        self.gh.active_since[REPO] = [{"databaseId": int(i), "status": "queued", "headBranch": b, "event": e,
                                       "createdAt": "2026-11-11T%s:00Z" % c} for i, b, e, c in rows]
        # build/checks finished on a light runner, the heavy jobs wait on the laptop
        jobs = [gh_job("preflight (affected & path filter)", "completed", "success", LIGHT),
                gh_job("vite build", "completed", "success", LIGHT), gh_job("checks", "in_progress", None, LIGHT),
                gh_job("Pest 1/3", labels=HEAVY), gh_job("Pest Postgres tenancy", labels=HEAVY)]
        for r, *_ in rows:
            self.gh.run_jobs[(REPO, r)] = jobs
            self.gh.runs[(REPO, r)] = "queued"

    def cancels(self):
        return [w[2] for w in self.gh.writes if w[0] == "force-cancel"]

    def quiet(self, extra=()):
        # quiet hour and day, CI on boat: room for 4 runs of 9 starts (60 - 15 kept free = 45)
        return self.tick([job("j1", state="success")] + boat_history(0) + list(extra), t("09:00"))

    def test_only_p1_runs_move_and_light_jobs_do_not_block(self):
        self.quiet()
        self.assertEqual(self.cancels(), ["302", "303", "305"], "feature-x and a PR from main stay on the laptop")

    def test_daily_cap_still_on_moves_nothing(self):
        paused = job("p1", repo=OTHER, run="77", queued="2026-11-11T08:30:00Z", reason=DAILY)  # resets 06:05 tomorrow
        self.quiet([paused])
        self.assertEqual(self.cancels(), [])

    def test_hourly_cap_still_on_moves_nothing(self):
        paused = job("p1", repo=OTHER, run="77", queued="2026-11-11T08:30:00Z", reason=HOURLY.replace("08:21", "09:30"))
        self.quiet([paused])
        self.assertEqual(self.cancels(), [])

    def test_cap_passed_does_not_block(self):
        paused = job("p1", repo=OTHER, run="77", queued="2026-11-11T07:30:00Z", reason=HOURLY)  # reset 08:21 < 09:00
        self.quiet([paused])
        self.assertEqual(self.cancels(), ["302", "303", "305"])

    def test_heavy_job_started_on_laptop_is_not_moved(self):
        self.gh.run_jobs[(REPO, "302")] = [gh_job("Pest 1/3", "in_progress", None, HEAVY), gh_job("Pest 2/3", labels=HEAVY)]
        self.quiet()
        self.assertEqual(self.cancels(), ["303", "305"])

    def test_non_p1_move_left_in_state_is_dropped_not_rerun(self):
        st = bf.load_state(self.state)
        st["moving"][REPO + "|301"] = {"since": "2026-11-11T08:59:00+00:00", "branch": "feature-x", "starts": 9,
                                        "wf": None, "event": "pull_request"}
        self.state.write_text(json.dumps(st))
        self.gh.runs[(REPO, "301")] = "completed"
        out = self.tick([job("j1", state="success")] + boat_history(40), t("09:00"))
        self.assertTrue(any("301 on feature-x is not P1" in line for line in out))
        self.assertFalse(any(w[0] == "rerun" and w[2] == "301" for w in self.gh.writes))


if __name__ == "__main__":
    unittest.main()
