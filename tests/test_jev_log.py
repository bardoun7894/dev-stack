"""Tests for bin/jev decision logging and `jev tune` ranking (no network)."""
import importlib.machinery
import importlib.util
import json
import os
import tempfile
import unittest

BIN = os.path.join(os.path.dirname(__file__), "..", "bin")


def load(name):
    loader = importlib.machinery.SourceFileLoader(name.replace("-", "_"), os.path.join(BIN, name))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


jev = load("jev")


class LogTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["JEV_LOG_DIR"] = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()
        del os.environ["JEV_LOG_DIR"]

    def read(self):
        with open(os.path.join(self.tmp.name, "decisions.jsonl")) as f:
            return [json.loads(line) for line in f]

    def test_log_decision_writes_one_record_with_id(self):
        q = {"type": "choice", "instructions": "Pick", "criteria": {"a": "x", "b": "y"}}
        did = jev.log_decision("t", {"k": "v"}, q, {"type": "choice", "choice": "a", "confidence": 0.9})
        recs = self.read()
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0]["id"], did)
        self.assertEqual(recs[0]["tag"], "t")
        self.assertEqual(recs[0]["value"], "a")
        self.assertEqual(recs[0]["confidence"], 0.9)

    def test_uncertainty(self):
        self.assertAlmostEqual(jev.uncertainty({"kind": "choice", "confidence": 0.9}), 0.1)
        self.assertAlmostEqual(jev.uncertainty({"kind": "noul", "value": 0.5}), 1.0)
        self.assertAlmostEqual(jev.uncertainty({"kind": "noul", "value": 1.0}), 0.0)
        self.assertEqual(jev.uncertainty({"kind": "choice", "confidence": None}), 1.0)

    def test_disagrees(self):
        self.assertTrue(jev.disagrees({"kind": "choice", "value": "a"}, "b"))
        self.assertFalse(jev.disagrees({"kind": "choice", "value": "a"}, "a"))
        self.assertTrue(jev.disagrees({"kind": "noul", "value": 0.9}, "no"))
        self.assertFalse(jev.disagrees({"kind": "noul", "value": 0.9}, "yes"))
        self.assertTrue(jev.disagrees({"kind": "score", "value": 2.8}, "1"))
        self.assertFalse(jev.disagrees({"kind": "score", "value": 2.8}, "3"))

    def test_tune_ranks_disagreements_then_uncertain(self):
        q = {"type": "choice", "instructions": "Pick", "criteria": {"a": "", "b": ""}}
        sure = jev.log_decision("t", "s1", q, {"type": "choice", "choice": "a", "confidence": 0.99})
        shaky = jev.log_decision("t", "s2", q, {"type": "choice", "choice": "a", "confidence": 0.4})
        wrong = jev.log_decision("t", "s3", q, {"type": "choice", "choice": "b", "confidence": 0.95})
        jev.log_decision("other", "s4", q, {"type": "choice", "choice": "a", "confidence": 0.1})
        jev.log_outcome(wrong, "a")
        report = jev.tune_report("t", n=5)
        self.assertEqual(report["decisions"], 3)
        self.assertEqual([r["id"] for r in report["disagreements"]], [wrong])
        self.assertEqual(report["uncertain"][0]["id"], shaky)
        self.assertNotIn(sure, [r["id"] for r in report["uncertain"][:1]])


class ErrorTest(unittest.TestCase):
    def test_post_raises_instead_of_exiting(self):
        old = jev.URL
        jev.URL = "http://127.0.0.1:9/nothing"
        os.environ["OPENROUTER_API_KEY"] = "test"
        try:
            with self.assertRaises(jev.JevError):
                jev.post({"model": "x", "state": "s", "questions": {}})
        finally:
            jev.URL = old
            del os.environ["OPENROUTER_API_KEY"]


class OpenRouterFallbackTest(unittest.TestCase):
    def run_post(self, ts_code):
        """TypeSafe answers ts_code (or 200); returns (urls hit, result or JevError)."""
        import io
        import urllib.error
        import urllib.request
        from unittest import mock
        urls = []

        def fake(req, timeout=None):
            urls.append(req.full_url)
            if req.full_url == jev.TYPESAFE_URL and ts_code != 200:
                raise urllib.error.HTTPError(req.full_url, ts_code, "x", {}, io.BytesIO(b"billing"))
            return io.BytesIO(b'{"answers": {"q": {"type": "score", "score": 3}}}')

        env = {"TYPESAFE_API_KEY": "ts", "OPENROUTER_API_KEY": "or", "JEV_NO_LAYA": "1"}
        with mock.patch.dict(os.environ, env), mock.patch.object(urllib.request, "urlopen", fake):
            os.environ.pop("JEV_DECISIONS_URL", None)
            try:
                return urls, jev.post({"model": jev.MODEL, "state": "s", "questions": {}})
            except jev.JevError as e:
                return urls, e

    def test_billing_error_retries_on_openrouter(self):
        for code in (401, 402, 403):
            urls, res = self.run_post(code)
            self.assertEqual(urls, [jev.TYPESAFE_URL, jev.URL])
            self.assertEqual(res["answers"]["q"]["score"], 3)

    def test_other_errors_do_not_retry(self):
        urls, res = self.run_post(500)
        self.assertEqual(urls, [jev.TYPESAFE_URL])
        self.assertIsInstance(res, jev.JevError)


if __name__ == "__main__":
    unittest.main()
