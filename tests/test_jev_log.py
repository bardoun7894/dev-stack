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

    def test_ask_many_logs_the_redacted_state(self):
        fake = "sk-or-v1-" + "abcdefghij" * 3  # assembled so secret scanners don't flag it
        sent = {}

        def fake_post(body, timeout=None):
            sent.update(body)
            return {"answers": {"q": {"type": "noul", "noul": 0.2}}}

        q = {"type": "noul", "instructions": "x"}
        old_post, jev.post = jev.post, fake_post
        os.environ["JEV_LOG_PREVIEW"] = "1"
        try:
            jev.ask_many({"excerpt": "OPENROUTER_API_KEY=" + fake}, {"q": q}, tag="t")
        finally:
            jev.post = old_post
            del os.environ["JEV_LOG_PREVIEW"]
        self.assertNotIn(fake, json.dumps(sent))
        line = json.dumps(self.read())
        self.assertNotIn(fake, line)
        self.assertIn("[REDACTED]", line)

    def test_log_decision_preview_is_redacted_even_if_caller_forgets(self):
        fake = "ghp" + "_" + "abcdefghij" * 3
        os.environ["JEV_LOG_PREVIEW"] = "1"
        try:
            jev.log_decision("t", "token " + fake, {"type": "noul"}, {"type": "noul", "noul": 0.1})
        finally:
            del os.environ["JEV_LOG_PREVIEW"]
        self.assertNotIn(fake, json.dumps(self.read()))

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


if __name__ == "__main__":
    unittest.main()
