"""Secrets never leave the machine: bin/jev_redact.py and every send path in bin/jev (no network).

Fake credentials are assembled at runtime so no key-shaped literal is committed.
"""
import io
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from test_jev_log import BIN, load

jev = load("jev")
red = jev.jev_redact
JEV = os.path.join(BIN, "jev")

FAKE = {
    "openrouter": "sk-or-v1-" + "a1B2c3D4e5F6" * 5,
    "openai": "sk-proj-" + "Zz9Yy8Xx7Ww6" * 3,
    "anthropic": "sk-ant-api03-" + "Qq1Rr2Ss3Tt4" * 3,
    "github": "ghp_" + "Ab12Cd34Ef56" * 3,
    "github_pat": "github_pat_" + "11AB22CD33" * 3,
    "aws": "AKIA" + "QWERTYUIOPASDFGH",
    "slack": "xoxb-" + "123456789012-" + "AbCdEfGhIjKl",
    "google": "AIza" + "Sy" + "B1c2D3e4F5g6H7i8J9k0L1m2N3o4P5q6R",
    "stripe": "sk_" + "live_" + "4eC39HqLyjWDarjtT1zdp7dc",
    "jwt": "eyJ" + "hbGciOiJIUzI1NiJ9" + ".eyJ" + "zdWIiOiIxMjM0NTY3ODkwIn0" + ".SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c",
    "entropy": "9fKq2LmZ8xR4tW7vB1nH3sD6gJ0pY5cE",
}
PEM_BODY = "MIIEpAIBAAKCAQEA" + "x" * 40
PEM = "-----BEGIN " + "RSA PRIVATE KEY-----\n" + PEM_BODY + "\n-----END RSA PRIVATE KEY-----"
PLAIN = {"pw": "hunter2-" + "horse", "env": "s3cr3t" + "Value99", "bearer": "Tk" + "9x8c7v6b5n4m3l2k1j"}

STATE = "\n".join([
    f"OPENROUTER_API_KEY={FAKE['openrouter']}",
    f"export OPENAI_API_KEY=\"{FAKE['openai']}\"",
    f"anthropic {FAKE['anthropic']} github {FAKE['github']} {FAKE['github_pat']}",
    f"aws {FAKE['aws']} slack {FAKE['slack']} google {FAKE['google']} stripe {FAKE['stripe']}",
    f"cookie jwt {FAKE['jwt']} blob {FAKE['entropy']}",
    f"password={PLAIN['pw']}",
    f"DB_SECRET: {PLAIN['env']}",
    f"Authorization: Bearer {PLAIN['bearer']}",
    f"git clone https://bob:{PLAIN['env']}@example.com/r.git",
    f"GET /cb?code=ok&access_token={PLAIN['bearer']}",
    PEM,
])
SECRETS = list(FAKE.values()) + list(PLAIN.values()) + [PEM_BODY]


def read(path):
    with open(path) as f:
        return f.read()


def leaked(text):
    return [s for s in SECRETS if s in text]


class RedactTest(unittest.TestCase):
    def test_every_secret_shape_is_masked(self):
        out = red.redact(STATE)
        self.assertEqual(leaked(out), [])
        self.assertIn("OPENROUTER_API_KEY=[REDACTED]", out)
        self.assertIn("Authorization: Bearer [REDACTED]", out)
        self.assertIn("https://bob:[REDACTED]@example.com", out)

    def test_structure_masks_secret_named_keys(self):
        out = red.redact({"api_key": "short1", "nested": [{"client_secret": PLAIN["pw"]}],
                          "headers": {"Authorization": "Bearer " + PLAIN["bearer"]}})
        self.assertEqual(out["api_key"], "[REDACTED]")
        self.assertEqual(out["nested"][0]["client_secret"], "[REDACTED]")
        self.assertEqual(leaked(json.dumps(out)), [])

    def test_ordinary_text_is_kept(self):
        keep = ("max_tokens=1000; token = os.environ['TOKEN']; commit 6a8f9dd271e7f4323372b64d22c8cc2081eb9951; "
                "see /usr/local/lib/python3.12/site-packages/x; log.info('password=%s', masked)")
        self.assertEqual(red.redact(keep), keep)
        self.assertEqual(red.redact({"criteria": {"token": "a label about tokens"}, "max_tokens": "1000"}),  # secret-scan:allow (test fixture)
                         {"criteria": {"token": "a label about tokens"}, "max_tokens": "1000"})  # secret-scan:allow (test fixture)

    def test_sensitive_paths(self):
        for p in (".env", "app/.env.production", "/home/u/.ssh/id_ed25519", "k.pem", "~/.aws/credentials",
                  "~/.local/share/opencode/auth.json", ".npmrc", "credentials-prod.json"):
            self.assertTrue(red.is_sensitive_path(p), p)
        for p in (".env.example", "README.md", "src/env.ts", "id_rsa.pub"):
            self.assertFalse(red.is_sensitive_path(p), p)


def capture_urlopen(answers):
    sent = []

    def fake(req, timeout=None):
        sent.append(req)
        return mock.MagicMock(__enter__=lambda s: io.BytesIO(json.dumps({"answers": answers}).encode()),
                              __exit__=lambda *a: False)
    return sent, fake


class SendPathTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = mock.patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key", "JEV_LOG_DIR": self.tmp.name,  # secret-scan:allow (test fixture)
                                                "JEV_LOG_PREVIEW": "1"})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_post_redacts_the_whole_body(self):
        sent, fake = capture_urlopen({})
        with mock.patch("urllib.request.urlopen", fake):
            jev.post({"state": STATE, "questions": {"q": {"type": "noul", "instructions": STATE}}, "extra": [STATE]})
        body = sent[0].data.decode()
        self.assertEqual(leaked(body), [])
        self.assertIn("[REDACTED]", body)

    def test_ask_many_and_decision_log_are_redacted(self):
        sent, fake = capture_urlopen({"q": {"type": "noul", "noul": 0.9}})
        with mock.patch("urllib.request.urlopen", fake):
            jev.ask_many({"code": STATE}, {"q": {"type": "noul", "instructions": "x " + FAKE["github"]}}, tag="t")
        self.assertEqual(leaked(sent[0].data.decode()), [])
        log = jev.log_path()
        self.assertEqual(leaked(read(log)), [])
        self.assertEqual(stat.S_IMODE(os.stat(log).st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(os.stat(os.path.dirname(log)).st_mode), 0o700)

    def test_raw_redacts_state_questions_and_extra_fields(self):
        sent, fake = capture_urlopen({"q": {"type": "noul", "noul": 0.2}})
        body = {"state": {"page": STATE}, "questions": {"q": {"type": "noul", "instructions": STATE}}, "note": STATE}
        with mock.patch("urllib.request.urlopen", fake), mock.patch("sys.stdin", io.StringIO(json.dumps(body))), \
                mock.patch("sys.stdout", io.StringIO()), mock.patch("sys.stderr", io.StringIO()):
            jev.main(["raw", "--log", "browse"])
        self.assertEqual(leaked(sent[0].data.decode()), [])
        self.assertEqual(leaked(read(jev.log_path())), [])

    def test_tune_redacts_legacy_unredacted_previews(self):
        jev._append({"kind_of_record": "decision", "id": "old", "tag": "t", "kind": "noul", "value": 0.5,
                     "state_preview": STATE[:600], "question": {"instructions": FAKE["openrouter"]}})
        self.assertEqual(leaked(json.dumps(jev.tune_report("t"))), [])

    def test_env_dry_run_prints_redacted_payload_and_sends_nothing(self):
        err = io.StringIO()
        with mock.patch.dict(os.environ, {"JEV_DRY_RUN": "1"}), mock.patch("sys.stderr", err), \
                mock.patch("urllib.request.urlopen", side_effect=AssertionError("network used")):
            with self.assertRaises(jev.JevError):
                jev.ask_many(STATE, {"q": {"type": "noul", "instructions": "x"}})
        out = json.loads(err.getvalue())
        self.assertTrue(out["dry_run"])
        self.assertIn("[REDACTED]", out["body"]["state"])
        self.assertEqual(leaked(err.getvalue()), [])

    def test_non_https_endpoint_never_gets_the_key(self):
        with mock.patch.object(jev, "URL", "http://evil.example/collect"), \
                mock.patch("urllib.request.urlopen", side_effect=AssertionError("network used")):
            with self.assertRaises(jev.JevError):
                jev.post({"state": "x"})

    def test_missing_redactor_fails_closed(self):
        with mock.patch.object(jev, "jev_redact", None), \
                mock.patch("urllib.request.urlopen", side_effect=AssertionError("network used")):
            with self.assertRaises(jev.JevError):
                jev.post({"state": "x"})

    def test_skill_suggest_prompt_is_redacted(self):
        sug = load("jev-skill-suggest")
        roster = {"alpha": {"description": "Does A.", "excerpt": "", "path": "/x"}}
        sent, fake = capture_urlopen({"skill": {"type": "choice", "choice": "alpha", "confidence": 0.1},
                                      "acts_on_user_system": {"noul": 0.1},
                                      "would_follow_documented_procedure": {"noul": 0.1},
                                      "prose_suffices": {"noul": 0.9}})
        with mock.patch("urllib.request.urlopen", fake):
            try:
                sug.suggest("deploy with this key " + STATE, roster, jev.ask_many)
            except Exception:
                pass
        self.assertTrue(sent)
        self.assertEqual(leaked(sent[0].data.decode()), [])

    def test_review_lint_snippets_are_redacted(self):
        rv = load("jev-review")
        sent, fake = capture_urlopen({"log-secret": {"type": "noul", "noul": 0.9}})
        cands = [{"file": "a.py", "line": 1, "kind": "log", "code": "log.info(" + repr(STATE) + ")"}]
        rules = [{"id": "log-secret", "level": "error", "question": "x", "applies_to": "log"}]
        with mock.patch("urllib.request.urlopen", fake):
            rv.lint(cands, rules, jev.ask_many)
        self.assertTrue(sent)
        for req in sent:
            self.assertEqual(leaked(req.data.decode()), [])


class CliTest(unittest.TestCase):
    """The real CLI in a subprocess, with no key and an empty HOME: anything but a dry run would fail."""

    def run_jev(self, args, stdin=""):
        with tempfile.TemporaryDirectory() as home:
            env = {k: v for k, v in os.environ.items() if k not in ("OPENROUTER_API_KEY", "JEV_DECISIONS_URL")}
            env.update(HOME=home, JEV_LOG_DIR=home)
            return subprocess.run([sys.executable, JEV, *args], input=stdin, capture_output=True, text=True,
                                  env=env, timeout=20)

    def test_raw_dry_run_shows_the_redacted_payload(self):
        body = {"state": {"page": STATE}, "questions": {"q": {"type": "noul", "instructions": "secret? " + FAKE["aws"]}}}
        r = self.run_jev(["raw", "--dry-run"], json.dumps(body))
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)
        self.assertTrue(out["dry_run"])
        self.assertIn("OPENROUTER_API_KEY=[REDACTED]", out["body"]["state"]["page"])
        self.assertEqual(leaked(r.stdout + r.stderr), [])

    def test_noul_dry_run(self):
        r = self.run_jev(["noul", "is this safe", "--state", STATE, "--dry-run"])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(leaked(r.stdout + r.stderr), [])
        self.assertIn("[REDACTED]", r.stdout)

    def test_state_file_refuses_env_files(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, ".env")
            with open(p, "w") as f:
                f.write("OPENROUTER_API_KEY=" + FAKE["openrouter"] + "\n")  # secret-scan:allow (test fixture)
            r = self.run_jev(["noul", "x", "-f", p, "--dry-run"])
        self.assertEqual(r.returncode, 64)
        self.assertEqual(leaked(r.stdout + r.stderr), [])


if __name__ == "__main__":
    unittest.main()
