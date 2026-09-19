"""Tests for bin/jev-review policy and parsing (Jev stubbed, no network)."""
import unittest

from test_jev_log import load

rv = load("jev-review")

DIFF = """diff --git a/app/auth.py b/app/auth.py
index 111..222 100644
--- a/app/auth.py
+++ b/app/auth.py
@@ -10,6 +10,7 @@ def login(user, password):
     if not user:
         return None
-    if user.disabled:
-        return None
+    log.info("login %s %s", user.email, password)
     return issue_token(user)
@@ -40,3 +40,3 @@ def logout(user):
-    session.clear()
+    session.clear(all=True)
diff --git a/package-lock.json b/package-lock.json
--- a/package-lock.json
+++ b/package-lock.json
@@ -1,1 +1,1 @@
-a
+b
diff --git a/img.png b/img.png
Binary files a/img.png and b/img.png differ
"""


class DiffTest(unittest.TestCase):
    def test_parse_hunks_skips_lockfiles_and_binaries(self):
        hunks = rv.parse_diff(DIFF)
        self.assertEqual([h["file"] for h in hunks], ["app/auth.py", "app/auth.py"])
        self.assertEqual(hunks[0]["new_start"], 10)
        self.assertIn('+    log.info("login %s %s", user.email, password)', hunks[0]["text"])
        self.assertIn("-    if user.disabled:", hunks[0]["text"])


class HunkStateTest(unittest.TestCase):
    def test_state_lists_other_changed_files(self):
        # Hunks are judged one at a time; without this, a hunk whose test lives in another file of the same
        # diff was flagged "no test" at 0.82-0.90 (real dev-stack diff, 2026-09-19).
        hunks = [{"file": "bin/tool", "text": "+x"}, {"file": "tests/test_tool.py", "text": "+t"},
                 {"file": "bin/tool", "text": "+y"}]
        s = rv.hunk_state(hunks[0], hunks)
        self.assertEqual(s["file"], "bin/tool")
        self.assertEqual(s["other_files_in_diff"], ["tests/test_tool.py"])


class RouteTest(unittest.TestCase):
    def f(self, dims, severity):
        return {"flagged": dims, "severity": severity}

    def test_nothing_flagged_routes_none(self):
        self.assertEqual(rv.route([]), "none")

    def test_low_severity_routes_reviewer(self):
        self.assertEqual(rv.route([self.f(["tests"], 0.8)]), "reviewer")

    def test_mid_severity_routes_codex(self):
        self.assertEqual(rv.route([self.f(["correctness"], 1.7)]), "codex")

    def test_high_security_routes_panel(self):
        self.assertEqual(rv.route([self.f(["security"], 2.7)]), "panel")

    def test_high_non_security_routes_codex(self):
        self.assertEqual(rv.route([self.f(["reliability"], 2.9)]), "codex")

    def test_tests_only_findings_never_escalate_past_reviewer(self):
        # Real dev-stack diff 2026-09-19: 8/8 flags were "tests" only and routed to codex; missing coverage
        # is a reviewer ask ("add a test"), not a second-opinion bug hunt.
        self.assertEqual(rv.route([self.f(["tests"], 1.9), self.f(["tests"], 2.6)]), "reviewer")
        self.assertEqual(rv.route([self.f(["tests"], 2.6), self.f(["reliability"], 1.6)]), "codex")

    def test_findings_from_answers(self):
        answers = {d: {"noul": 0.1} for d in rv.DIMENSIONS}
        answers["security"] = {"noul": 0.92}
        answers["severity"] = {"score": 2.6, "confidence": 0.8}
        f = rv.finding({"file": "a.py", "new_start": 3, "text": "+x"}, answers)
        self.assertEqual(f["flagged"], ["security"])
        self.assertEqual(f["severity"], 2.6)
        self.assertEqual(rv.finding({"file": "a", "new_start": 1, "text": ""},
                                    {**{d: {"noul": 0.1} for d in rv.DIMENSIONS},
                                     "severity": {"score": 0.2}})["flagged"], [])


class GitFailClosedTest(unittest.TestCase):
    def test_git_failure_raises_instead_of_empty_diff(self):
        # On MyContabo, "dubious ownership" made git print nothing and the review said "route: none".
        with self.assertRaises(rv.GitError):
            rv.git("/nonexistent-dir-for-jev-review-test", "diff", "HEAD")


class CandidatesTest(unittest.TestCase):
    SRC = [
        "import logging",
        "# increment i by one",
        "i += 1",
        "def save_user(u):",
        "    logging.info('saved %s', u.email)",
        "    db.write(u)",
        "function getTotal(items) {",
        "  console.log(token)",
        "}",
    ]

    def test_extracts_logs_functions_comments(self):
        kinds = {(c["kind"], c["line"]) for c in rv.candidates("x.py", self.SRC)}
        self.assertIn(("comment", 2), kinds)
        self.assertIn(("function", 4), kinds)
        self.assertIn(("log", 5), kinds)
        self.assertIn(("function", 7), kinds)
        self.assertIn(("log", 8), kinds)
        self.assertNotIn(("log", 1), kinds)


class EstimateTest(unittest.TestCase):
    def test_estimate_counts_tokens_and_cost(self):
        est = rv.estimate(["a" * 4000, "b" * 400], question_tokens=250)
        self.assertEqual(est["requests"], 2)
        self.assertEqual(est["input_tokens"], 1000 + 100 + 2 * 250)
        self.assertAlmostEqual(est["cost_usd"], 1600 * 0.042 / 1_000_000)


class LintTest(unittest.TestCase):
    def test_error_level_hit_sets_exit_code(self):
        rules = [{"id": "log-secret", "level": "error", "applies_to": "log", "question": "q", "threshold": 0.7},
                 {"id": "log-pii", "level": "warn", "applies_to": "log", "question": "q2", "threshold": 0.7}]
        cands = [{"file": "a.py", "line": 5, "kind": "log", "code": "log(password)"}]

        def fake(state, questions, tag=None, timeout=None):
            return ({"log-secret": {"noul": 0.95}, "log-pii": {"noul": 0.2}}, {}, 0.00001)

        hits, code = rv.lint(cands, rules, fake)
        self.assertEqual([(h["rule"], h["level"]) for h in hits], [("log-secret", "error")])
        self.assertEqual(code, 1)

    def test_warn_only_exits_zero(self):
        rules = [{"id": "log-pii", "level": "warn", "applies_to": "log", "question": "q", "threshold": 0.7}]
        cands = [{"file": "a.py", "line": 5, "kind": "log", "code": "log(email)"}]
        hits, code = rv.lint(cands, rules, lambda *a, **k: ({"log-pii": {"noul": 0.9}}, {}, 0))
        self.assertEqual(len(hits), 1)
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
