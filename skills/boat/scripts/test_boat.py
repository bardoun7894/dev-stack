import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boat  # noqa: E402

SENTINEL = "dummy-test-value-not-real"


class Fake:
    """Fake HTTP layer replacing boat._transport."""

    def __init__(self, exit_code=0, running_polls=1):
        self.calls = []
        self.exit_code = exit_code
        self.polls = running_polls

    def __call__(self, req, timeout):
        url = req.full_url
        path = url.replace(boat.BASE, "")
        body = json.loads(req.data) if req.data and req.data[:1] == b"{" else None
        self.calls.append((req.get_method(), path, body, dict(req.header_items())))
        m = req.get_method()
        if m == "POST" and path == "/sandboxes":
            return 200, b'{"sandbox":{"id":"bx_1","state":"cloning"}}'
        if m == "GET" and path == "/sandboxes/bx_1":
            return 200, b'{"sandbox":{"id":"bx_1","state":"ready"}}'
        if m == "POST" and path.endswith("/files/upload-url"):
            return 200, b'{"url":"https://signed.example/up"}'
        if m == "PUT":
            return 200, b""
        if m == "POST" and path.endswith("/commands"):
            if body.get("detached"):
                return 200, b'{"type":"command.started","processId":42}'
            if self.exit_code == 99:
                return 500, b'{"error":"boom ' + SENTINEL.encode() + b'"}'
            return 200, json.dumps({"exitCode": self.exit_code, "stdout": "hi\n", "stderr": ""}).encode()
        if m == "GET" and "/commands/42" in path:
            self.polls -= 1
            if self.polls > 0:
                return 200, b'{"running":true,"stdout":"a","stdoutNextOffset":1,"stderrNextOffset":0,"more":false}'
            return 200, b'{"running":false,"exitCode":3,"stdout":"b","stdoutNextOffset":2,"stderrNextOffset":0}'
        if m == "DELETE" and path == "/sandboxes/bx_1":
            return 202, b'{"operation":{"id":"bdop_1","status":"pending"}}'
        if m == "GET" and path.startswith("/deletion-operations/"):
            return 200, b'{"operation":{"status":"completed"}}'
        return 404, b'{"error":"unexpected %s %s"}' % (m.encode(), path.encode())

    def paths(self, method=None):
        return [(m, p) for m, p, _, _ in self.calls if method in (None, m)]


class Base(unittest.TestCase):
    def setUp(self):
        self.env = mock.patch.dict(os.environ, {"BOAT_API_KEY": SENTINEL})
        self.env.start()
        self.sleep = mock.patch.object(boat.time, "sleep", lambda s: None)
        self.sleep.start()

    def tearDown(self):
        self.env.stop()
        self.sleep.stop()

    def run_main(self, fake, argv):
        o, e = io.StringIO(), io.StringIO()
        with mock.patch.object(boat, "_transport", fake), \
                contextlib.redirect_stdout(o), contextlib.redirect_stderr(e):
            code = boat.main(argv)
        return code, o.getvalue(), e.getvalue()


class TestKey(Base):
    def test_key_never_printed(self):
        f = Fake(exit_code=99)  # server error echoing the key
        code, o, e = self.run_main(f, ["exec", "bx_1", "--", "echo hi"])
        self.assertNotEqual(code, 0)
        self.assertNotIn(SENTINEL, o + e)
        self.assertIn("Bearer " + SENTINEL, f.calls[0][3]["Authorization"])

    def test_key_file_fallback(self):
        with tempfile.TemporaryDirectory() as d:
            kf = Path(d) / "key"
            kf.write_text("filekey\n")
            with mock.patch.dict(os.environ, {}, clear=False):
                os.environ.pop("BOAT_API_KEY", None)
                with mock.patch.object(boat, "KEY_FILE", kf):
                    self.assertEqual(boat.get_key(), "filekey")


class TestExec(Base):
    def test_sync_under_limit(self):
        f = Fake(exit_code=7)
        code, o, _ = self.run_main(f, ["exec", "bx_1", "--timeout", "600", "--", "false"])
        self.assertEqual(code, 7)
        body = f.calls[0][2]
        self.assertEqual(body["timeoutSeconds"], 600)
        self.assertNotIn("detached", body)

    def test_detached_above_600(self):
        f = Fake(running_polls=2)
        code, o, _ = self.run_main(f, ["exec", "bx_1", "--timeout", "900", "--", "long"])
        self.assertEqual(code, 3)
        self.assertTrue(f.calls[0][2].get("detached"))
        self.assertTrue(any("/commands/42" in p for _, p in f.paths("GET")))
        self.assertEqual(o, "ab")  # incremental output


class TestRun(Base):
    def test_run_deletes_even_when_command_fails(self):
        f = Fake(exit_code=5)
        code, _, _ = self.run_main(f, ["run", "--", "false"])
        self.assertEqual(code, 5)
        self.assertIn(("DELETE", "/sandboxes/bx_1"), f.paths())
        d = [c for c in f.calls if c[0] == "DELETE"][0]
        self.assertEqual(d[3]["X-ascii-confirm-delete"], "bx_1")

    def test_run_deletes_when_api_errors(self):
        f = Fake(exit_code=99)
        code, _, e = self.run_main(f, ["run", "--", "x"])
        self.assertEqual(code, 1)
        self.assertIn(("DELETE", "/sandboxes/bx_1"), f.paths())
        self.assertNotIn(SENTINEL, e)

    def test_new_deletes_when_never_ready(self):
        class F(Fake):
            def __call__(self, req, timeout):
                if req.get_method() == "GET" and req.full_url.endswith("/sandboxes/bx_1"):
                    self.calls.append(("GET", "/sandboxes/bx_1", None, {}))
                    raise KeyboardInterrupt
                return super().__call__(req, timeout)
        f = F()
        with self.assertRaises(KeyboardInterrupt):
            self.run_main(f, ["new"])
        self.assertIn(("DELETE", "/sandboxes/bx_1"), f.paths())

    def test_create_sends_ttl_and_idempotency(self):
        f = Fake()
        self.run_main(f, ["run", "--size", "small", "--", "true"])
        m, p, body, h = f.calls[0]
        self.assertEqual(body, {"ttlSeconds": 3600, "type": "small"})
        self.assertIn("Idempotency-key", h)


class TestPush(Base):
    def test_push_only_tracked(self):
        with tempfile.TemporaryDirectory() as d:
            subprocess.run(["git", "init", "-q", d], check=True)
            Path(d, "a.txt").write_text("a")
            Path(d, "ignored.log").write_text("x")
            subprocess.run(["git", "-C", d, "add", "a.txt"], check=True)
            import tarfile
            names = tarfile.open(fileobj=io.BytesIO(boat.make_tarball(d))).getnames()
            self.assertEqual(names, ["a.txt"])


class TestCi(Base):
    def test_ci_enable_rewrites(self):
        with tempfile.TemporaryDirectory() as d:
            wf = Path(d, "proj", ".github", "workflows")
            wf.mkdir(parents=True)
            (wf / "ci.yml").write_text("jobs:\n  t:\n    runs-on: ubuntu-latest\n  u:\n    runs-on: [ubuntu-latest]\n    runs-on: macos-latest\n")
            code, o, _ = self.run_main(Fake(), ["ci", "enable", str(Path(d, "proj"))])
            self.assertEqual(code, 0)
            txt = (wf / "ci.yml").read_text()
            self.assertEqual(txt.count("runs-on: boat"), 2)
            self.assertIn("macos-latest", txt)
            self.assertIn("-    runs-on: ubuntu-latest", o)

    def test_ci_enable_allows_mediatgb(self):
        # Owner 2026-11-11: MEDIA TGB CI runs on boat; the 2026-11-02 block is gone.
        with tempfile.TemporaryDirectory() as d:
            wf = Path(d, "mediatgb", ".github", "workflows")
            wf.mkdir(parents=True)
            (wf / "ci.yml").write_text("runs-on: ubuntu-latest\n")
            code, _, e = self.run_main(Fake(), ["ci", "enable", str(Path(d, "mediatgb"))])
            self.assertEqual(code, 0)
            self.assertIn("runs-on: boat", (wf / "ci.yml").read_text())


class TestCleanup(Base):
    def test_dry_run_default(self):
        class F(Fake):
            def __call__(s, req, timeout):
                if req.get_method() == "GET" and req.full_url.endswith("/sandboxes"):
                    return 200, b'{"sandboxes":[{"id":"bx_1","state":"idle","createdAt":"2020-01-01T00:00:00Z"}]}'
                return super().__call__(req, timeout)
        f = F()
        code, o, _ = self.run_main(f, ["cleanup", "--older-than", "1"])
        self.assertEqual(code, 0)
        self.assertNotIn(("DELETE", "/sandboxes/bx_1"), f.paths())
        f2 = F()
        self.run_main(f2, ["cleanup", "--older-than", "1", "--yes"])
        self.assertIn(("DELETE", "/sandboxes/bx_1"), f2.paths())


if __name__ == "__main__":
    unittest.main()
