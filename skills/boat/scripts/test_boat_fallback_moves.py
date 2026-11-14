"""Spec 003 D8: runs stranded on the fallback move back to boat (T8). Shared fake gh and helpers live in
test_boat_fallback.py."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boat_fallback as bf  # noqa: E402
from test_boat_fallback import OTHER, REPO, Base, job, t  # noqa: E402

LAPTOP = ["self-hosted", "cachy"]


def gh_job(name, status="queued", conclusion=None, labels=LAPTOP):
    return {"name": name, "status": status, "conclusion": conclusion, "labels": labels}


def boat_history(n_started, at="07:30", names=9):
    """Boat jobs of earlier runs: one run with `names` distinct jobs, plus `n_started` starts at `at`."""
    hist = [dict(job("h%d" % i, run="90", state="success"), jobName="J%d" % i, runStartedAt="2026-11-11T05:00:00Z")
            for i in range(names)]
    hist += [dict(job("s%d" % i, run=str(91 + i // names), state="success"), jobName="J%d" % (i % names),
                  runStartedAt="2026-11-11T%s:00Z" % at) for i in range(n_started)]
    return hist


def started_on_boat(*runs, at="07:59"):
    """Boat jobs showing these runs started (one job each)."""
    return [dict(job("b" + r, run=r, state="success"), jobName="preflight", runStartedAt="2026-11-11T%s:00Z" % at)
            for r in runs]


class T8MoveStranded(Base):
    """On restore, runs that have not started on the fallback go back to boat, oldest first, within boat's room."""

    def setUp(self):
        super().setUp()
        rows = [("201", "queued", "a", "07:20"), ("202", "queued", "b", "07:25"), ("203", "queued", "c", "07:30"),
                ("204", "queued", "c", "07:35"), ("206", "queued", "d", "07:40"), ("205", "completed", "e", "07:15")]
        self.gh.active_since[REPO] = [{"databaseId": int(i), "status": s, "headBranch": b,
                                       "createdAt": "2026-11-11T%s:00Z" % c} for i, s, b, c in rows]
        unstarted = [gh_job("preflight (affected & path filter)"), gh_job("ci-ok")]
        for run in ("201", "203", "204", "206"):
            self.gh.run_jobs[(REPO, run)] = unstarted
            self.gh.runs[(REPO, run)] = "queued"
        self.gh.run_jobs[(REPO, "202")] = [gh_job("preflight", "completed", "success"), gh_job("Pest 1/3", "in_progress")]
        self.gh.runs[(REPO, "202")] = "in_progress"

    def restore(self, n_started):
        self.tick([job("j1")], t("07:12"))
        return self.tick([job("j1")] + boat_history(n_started), t("07:56"))

    def cancels(self):
        return [w[2] for w in self.gh.writes if w[0] == "force-cancel"]

    def cancelled(self, *runs):
        for run in runs:
            self.gh.runs[(REPO, run)] = "completed"

    def test_moves_oldest_unstarted_newest_per_branch_within_room(self):
        self.restore(20)  # room: 60 - 15 kept free - 20 used = 25 starts = 2 runs of 9
        self.assertEqual(self.gh.vars[REPO]["CI_RUNS_ON"], '"boat"')
        self.assertEqual(self.cancels(), ["201", "204"], "202 started, 203 superseded by 204, 206 over the room")
        self.assertFalse(any(w[0] == "rerun" and w[2] != "100" for w in self.gh.writes), "no rerun before the cancel lands")
        self.cancelled("201", "204")
        self.tick([job("j1")] + boat_history(20), t("07:58"))
        reruns = [w for w in self.gh.writes if w[0] == "rerun" and w[2] != "100"]
        self.assertEqual(reruns, [("rerun", REPO, "201", False), ("rerun", REPO, "204", False)], "full reruns")
        self.assertEqual(self.cancels(), ["201", "204"], "reruns not started on boat yet still use the room")
        self.tick([job("j1")] + boat_history(20) + started_on_boat("201", "204"), t("08:00"))
        moving = bf.load_state(self.state)["moving"]
        self.assertNotIn(REPO + "|201", moving, "started on boat: no longer counted as pending")
        self.assertNotIn(REPO + "|204", moving)

    def test_superseded_after_cancel_is_not_rerun(self):
        self.restore(20)
        self.cancelled("201", "204")
        self.gh.active_since[REPO].append({"databaseId": 207, "status": "queued", "headBranch": "a",
                                           "createdAt": "2026-11-11T07:57:00Z"})
        self.tick([job("j1")] + boat_history(20), t("07:58"))
        reruns = [w[2] for w in self.gh.writes if w[0] == "rerun" and w[2] != "100"]
        self.assertEqual(reruns, ["204"], "a newer push on branch a replaced 201")

    def test_no_room_moves_nothing(self):
        self.restore(40)  # 60 - 15 - 40 = 5 starts: not one run
        self.assertEqual(self.gh.vars[REPO]["CI_RUNS_ON"], '"boat"')
        self.assertEqual(self.cancels(), [])

    def test_cancel_that_never_completes_is_dropped(self):
        self.restore(20)  # 201 and 204 stay queued: the cancel never lands
        self.tick([job("j1")] + boat_history(20), t("08:10"))
        self.assertEqual(sorted(bf.load_state(self.state)["moving"]), [REPO + "|201", REPO + "|204"], "still waiting")
        self.assertEqual(self.cancels(), ["201", "204"], "pending moves are not cancelled twice")
        out = self.tick([job("j1")], t("08:40"))
        self.assertTrue(any("201 still not cancelled" in line for line in out))
        self.assertFalse(any(w[0] == "rerun" and w[2] in ("201", "204") for w in self.gh.writes))

    def test_stranded_while_already_on_boat(self):
        # No fallback state at all (CI already back on boat, e.g. restored by an older watcher): still moved.
        self.tick([job("j1", state="success")] + boat_history(20, at="08:50"), t("09:00"))
        self.assertEqual(self.cancels(), ["201", "204"])

    def test_pending_moves_use_room(self):
        self.tick([job("j1", state="success")] + boat_history(20, at="08:50"), t("09:00"))  # room 2: 201, 204
        self.tick([job("j1", state="success")] + boat_history(20, at="08:50"), t("09:02"))  # 2 moves pending: 25 - 18 -> 0 runs
        self.assertEqual(self.cancels(), ["201", "204"], "206 waits until the moved runs are on boat")
        self.cancelled("201", "204")
        self.tick([job("j1", state="success")] + boat_history(20, at="08:50"), t("09:04"))  # reran, not started on boat
        self.assertEqual(self.cancels(), ["201", "204"], "queued reruns on boat still use the room")
        # An hour later: the 08:50 starts have aged out, the two reruns started on boat at 09:05 (18 starts) -> room 3.
        self.tick([job("j1", state="success")] + boat_history(20, at="08:50")
                  + [dict(j, jobName="J%d" % i) for r in ("201", "204")
                     for i, j in enumerate(started_on_boat(*[r] * 9, at="09:05"))], t("10:00"))
        self.assertEqual(self.cancels(), ["201", "204", "206"])

    def test_fallback_repo_checked_without_boat_jobs(self):
        self.tick([job("j1")], t("07:12"))
        self.tick([job("j1")] + boat_history(40), t("07:56"))  # restore with no room: nothing moved yet
        self.assertEqual(self.cancels(), [])
        other = [dict(job("o1", repo=OTHER, state="success"), jobName="x", runStartedAt="2026-11-11T08:59:00Z")]
        self.tick(other, t("09:00"))  # boat lists no job of REPO any more; the repo is remembered
        self.assertEqual(self.cancels(), ["201", "204", "206"], "13 starts per run when unknown: room 3")

    def test_fallback_active_moves_nothing(self):
        self.tick([job("j1")] + boat_history(0), t("07:12"))  # boat full: CI on the fallback
        self.assertEqual(self.cancels(), [])

    def test_dry_run_moves_nothing(self):
        self.tick([job("j1")], t("07:12"))
        n = len(self.gh.writes)
        self.tick([job("j1")] + boat_history(20), t("07:56"), dry=True)
        self.assertEqual(len(self.gh.writes), n)


if __name__ == "__main__":
    unittest.main()
