"""Tests for bin/quota-snapshot: fixtures for the Claude oauth usage JSON, codex session logs and run-record estimates."""
import importlib.machinery
import importlib.util
import json
import os
import tempfile
import time
import unittest
from datetime import datetime, timezone, timedelta

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
PATH = os.path.join(ROOT, "bin", "quota-snapshot")
loader = importlib.machinery.SourceFileLoader("quota_snapshot", PATH)
spec = importlib.util.spec_from_loader("quota_snapshot", loader)
qs = importlib.util.module_from_spec(spec)
loader.exec_module(qs)

NOW = datetime(2026, 10, 3, 12, 0, 0, tzinfo=timezone.utc)


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def token_event(ts, primary, secondary=None):
    return json.dumps({"timestamp": iso(ts), "type": "event_msg", "payload": {"type": "token_count", "rate_limits": {"primary": primary, "secondary": secondary}}})


class ClaudeTest(unittest.TestCase):
    def test_parses_usage(self):
        body = {"five_hour": {"utilization": 42.0, "resets_at": "2026-10-03T15:00:00Z"},
                "seven_day": {"utilization": 92, "resets_at": "2026-10-07T00:00:00Z"}}
        r = qs.parse_claude(body)
        self.assertEqual(r["source"], "api")
        self.assertAlmostEqual(r["five_hour"], 0.42)
        self.assertAlmostEqual(r["weekly"], 0.92)
        self.assertIsNone(r["monthly"])
        self.assertEqual(r["resets"]["weekly"], "2026-10-07T00:00:00Z")

    def test_missing_window_is_null(self):
        r = qs.parse_claude({"five_hour": None, "seven_day": {"utilization": 10}})
        self.assertIsNone(r["five_hour"])
        self.assertAlmostEqual(r["weekly"], 0.1)

    def test_garbage_is_error(self):
        self.assertEqual(qs.parse_claude(["x"])["source"], "error")

    def test_no_credentials_is_error(self):
        with tempfile.TemporaryDirectory() as d:
            r = qs.claude_quota(creds_path=os.path.join(d, "none.json"), use_keychain=False, fetch=lambda *a: self.fail("no call"))
        self.assertEqual(r["source"], "error")
        self.assertIsNone(r["weekly"])

    def test_token_from_file_never_in_result(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "c.json")
            json.dump({"claudeAiOauth": {"accessToken": "SECRET-TOKEN"}}, open(p, "w"))
            seen = {}

            def fetch(url, headers, timeout):
                seen.update(headers)
                return {"five_hour": {"utilization": 5}, "seven_day": {"utilization": 6}}
            r = qs.claude_quota(creds_path=p, use_keychain=False, fetch=fetch)
        self.assertEqual(seen["Authorization"], "Bearer SECRET-TOKEN")
        self.assertEqual(seen["anthropic-beta"], "oauth-2025-04-20")
        self.assertNotIn("SECRET-TOKEN", json.dumps(r))

    def test_fetch_failure_is_error_without_token(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "c.json")
            json.dump({"claudeAiOauth": {"accessToken": "SECRET-TOKEN"}}, open(p, "w"))

            def fetch(*a):
                raise OSError("boom SECRET-TOKEN")
            r = qs.claude_quota(creds_path=p, use_keychain=False, fetch=fetch)
        self.assertEqual(r["source"], "error")
        self.assertNotIn("SECRET-TOKEN", json.dumps(r))


class CodexTest(unittest.TestCase):
    def write(self, d, name, lines):
        p = os.path.join(d, "2026", "10", "03")
        os.makedirs(p, exist_ok=True)
        f = os.path.join(p, name)
        with open(f, "w") as fh:
            fh.write("\n".join(lines) + "\n")
        return f

    def test_skips_primary_null_and_maps_windows(self):
        with tempfile.TemporaryDirectory() as d:
            reset5 = int((NOW + timedelta(hours=2)).timestamp())
            resetw = int((NOW + timedelta(days=3)).timestamp())
            self.write(d, "a.jsonl", [
                token_event(NOW - timedelta(minutes=30), {"used_percent": 25.0, "window_minutes": 300, "resets_at": reset5},
                            {"used_percent": 60.0, "window_minutes": 10080, "resets_at": resetw}),
                token_event(NOW - timedelta(minutes=1), None, None),
            ])
            r = qs.codex_quota(d, now=NOW)
        self.assertEqual(r["source"], "local")
        self.assertAlmostEqual(r["five_hour"], 0.25)
        self.assertAlmostEqual(r["weekly"], 0.60)
        self.assertIsNone(r["monthly"])

    def test_weekly_only_primary(self):
        with tempfile.TemporaryDirectory() as d:
            resetw = int((NOW + timedelta(days=3)).timestamp())
            self.write(d, "a.jsonl", [token_event(NOW, {"used_percent": 12.0, "window_minutes": 10080, "resets_at": resetw})])
            r = qs.codex_quota(d, now=NOW)
        self.assertIsNone(r["five_hour"])
        self.assertAlmostEqual(r["weekly"], 0.12)

    def test_window_past_its_reset_counts_as_zero(self):
        with tempfile.TemporaryDirectory() as d:
            reset5 = int((NOW - timedelta(hours=1)).timestamp())
            resetw = int((NOW + timedelta(days=1)).timestamp())
            self.write(d, "a.jsonl", [token_event(NOW - timedelta(hours=6), {"used_percent": 99.0, "window_minutes": 300, "resets_at": reset5},
                                                  {"used_percent": 40.0, "window_minutes": 10080, "resets_at": resetw})])
            r = qs.codex_quota(d, now=NOW)
        self.assertEqual(r["five_hour"], 0.0)
        self.assertAlmostEqual(r["weekly"], 0.40)
        self.assertIn("age", r["note"])

    def test_no_sessions_is_error(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(qs.codex_quota(d, now=NOW)["source"], "error")
        self.assertEqual(qs.codex_quota("/nonexistent/dir", now=NOW)["source"], "error")

    def test_only_null_snapshots_is_error(self):
        with tempfile.TemporaryDirectory() as d:
            self.write(d, "a.jsonl", [token_event(NOW, None), "not json"])
            self.assertEqual(qs.codex_quota(d, now=NOW)["source"], "error")


class EstimateTest(unittest.TestCase):
    def run_dir(self, cache, ts, provider, cmd="opencode run -m", dry=False):
        name = ts.strftime("%Y-%m-%dT%H-%M-%S-000Z") + "-job-" + provider + ("-dry" if dry else "")
        d = os.path.join(cache, name)
        os.makedirs(d)
        with open(os.path.join(d, "run.sh"), "w") as f:
            f.write(f"#!/bin/bash\n{cmd} '{provider}/some-model' --dir x\n")
        if dry:
            open(os.path.join(d, "dry-run"), "w").close()

    def test_counts_per_window_against_caps(self):
        caps = {"opencode-go": {"five_hour": 10, "weekly": 100, "monthly": 400}}
        with tempfile.TemporaryDirectory() as c:
            for h in (1, 2):
                self.run_dir(c, NOW - timedelta(hours=h), "opencode-go")
            self.run_dir(c, NOW - timedelta(days=3), "opencode-go")
            self.run_dir(c, NOW - timedelta(days=20), "opencode-go")
            self.run_dir(c, NOW - timedelta(days=40), "opencode-go")
            self.run_dir(c, NOW - timedelta(hours=1), "opencode-go", dry=True)
            self.run_dir(c, NOW - timedelta(hours=1), "commandcode", cmd="pi --model")
            r = qs.estimate_quota("opencode-go", c, caps, now=NOW)
        self.assertEqual(r["source"], "estimate")
        self.assertAlmostEqual(r["five_hour"], 0.2)
        self.assertAlmostEqual(r["weekly"], 0.03)
        self.assertAlmostEqual(r["monthly"], 0.01)

    def test_usage_is_capped_at_one(self):
        caps = {"commandcode": {"five_hour": 1, "weekly": 1, "monthly": 1}}
        with tempfile.TemporaryDirectory() as c:
            for h in (1, 2, 3):
                self.run_dir(c, NOW - timedelta(hours=h), "commandcode", cmd="pi --model")
            r = qs.estimate_quota("commandcode", c, caps, now=NOW)
        self.assertEqual(r["five_hour"], 1.0)

    def test_missing_caps_or_cache_dir(self):
        self.assertEqual(qs.estimate_quota("opencode-go", "/nonexistent", {}, now=NOW)["source"], "error")
        r = qs.estimate_quota("opencode-go", "/nonexistent", {"opencode-go": {"five_hour": 5, "weekly": 5, "monthly": 5}}, now=NOW)
        self.assertEqual(r["five_hour"], 0.0)


class SnapshotTest(unittest.TestCase):
    def test_sources_fail_soft_independently(self):
        def boom():
            raise RuntimeError("x")
        snap = qs.build_snapshot({"a": lambda: {"five_hour": 0.1, "weekly": None, "monthly": None, "resets": {}, "source": "api", "note": ""}, "b": boom}, now=NOW)
        self.assertEqual(snap["providers"]["a"]["source"], "api")
        self.assertEqual(snap["providers"]["b"]["source"], "error")
        self.assertIsNone(snap["providers"]["b"]["weekly"])
        self.assertTrue(snap["at"].startswith("2026-10-03"))
        self.assertEqual(snap["providers"]["a"]["at"], snap["at"])

    def test_atomic_write(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "sub", "quota.json")
            qs.write_atomic(out, {"at": "x", "providers": {}})
            self.assertEqual(json.load(open(out))["at"], "x")
            self.assertEqual(os.listdir(os.path.dirname(out)), ["quota.json"])
            qs.write_atomic(out, {"at": "y", "providers": {}})
            self.assertEqual(json.load(open(out))["at"], "y")
            self.assertEqual(os.listdir(os.path.dirname(out)), ["quota.json"])


if __name__ == "__main__":
    unittest.main()
