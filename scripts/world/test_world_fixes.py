#!/usr/bin/env python3
"""Unit tests for world-push / track error handling, token loading and collectors (no network)."""
import importlib.machinery
import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
os.environ.setdefault("WORLD_STATE_DIR", tempfile.mkdtemp(prefix="worldfix."))

import lib_world  # noqa: E402


def load_script(name):
    loader = importlib.machinery.SourceFileLoader(name.replace("-", "_"), str(HERE / name))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


world_push = load_script("world-push")
import world_push_sources as wps  # noqa: E402
track = load_script("track")


class FakeServer:
    """post_events stand-in: refuses any batch containing a 'bad' event, with or without an index."""

    def __init__(self, code=400, name_index=False):
        self.code, self.name_index, self.calls = code, name_index, 0

    def __call__(self, batch, url=None, timeout=5.0, token=None):
        self.calls += 1
        bad = [i for i, ev in enumerate(batch) if ev.get("bad")]
        if bad:
            where = f"event {bad[0]}: title too long" if self.name_index else "invalid payload"
            raise RuntimeError(f"server rejected {self.code}: {where}")
        return {"accepted": len(batch), "duplicate": 0}


def evs(n, bad=()):
    return [{"id": str(i), "bad": i in bad} for i in range(n)]


class PayloadRejection(unittest.TestCase):
    def test_classification(self):
        for msg in ("server rejected 400: x", "server rejected 413: big", "server rejected 422: event 2: y"):
            self.assertTrue(lib_world.payload_rejection(msg), msg)
        for msg in ("server rejected 500: event 1: boom", "server rejected 503: x", "server rejected 401: no",
                    "server rejected 403: no", "server rejected 404: x", "server rejected 429: slow",
                    "transport: timed out", ""):
            self.assertFalse(lib_world.payload_rejection(msg), msg)


class SendDroppingRejects(unittest.TestCase):
    def run_send(self, events, server, chunk=500):
        rejected = []
        with mock.patch.object(lib_world, "post_events", server), \
                mock.patch.object(lib_world, "rejected_append", lambda ev, msg: rejected.append(ev["id"])):
            total = world_push.send_dropping_rejects(events, url="u", timeout=1, token="", chunk=chunk)
        return total, rejected

    def test_unidentified_4xx_is_bisected_to_the_bad_event(self):
        total, rejected = self.run_send(evs(10, bad={7}), FakeServer(400))
        self.assertEqual(rejected, ["7"])
        self.assertEqual(total, {"accepted": 9, "duplicate": 0, "rejected": 1})

    def test_two_bad_events_across_chunks(self):
        total, rejected = self.run_send(evs(9, bad={0, 5}), FakeServer(422), chunk=4)
        self.assertEqual(sorted(rejected), ["0", "5"])
        self.assertEqual(total["accepted"], 7)

    def test_indexed_4xx_still_drops_just_that_event(self):
        server = FakeServer(400, name_index=True)
        total, rejected = self.run_send(evs(6, bad={2}), server)
        self.assertEqual((rejected, total["accepted"], server.calls), (["2"], 5, 2))

    def test_5xx_and_auth_errors_raise_and_reject_nothing(self):
        for code in (500, 502, 401, 403, 429):
            with self.subTest(code=code):
                with self.assertRaises(RuntimeError):
                    self.run_send(evs(3, bad={1}), FakeServer(code, name_index=True))


class TrackFlush(unittest.TestCase):
    def flush(self, err):
        box = [{"id": "a", "title": "t"}, {"id": "b", "title": "t"}]
        state = {"outbox": list(box), "rejected": []}

        def post(batch, url=None, timeout=5.0, token=None):
            raise RuntimeError(err)
        with mock.patch.object(track, "post_events", post), \
                mock.patch.object(track, "outbox_load", lambda: list(state["outbox"])), \
                mock.patch.object(track, "outbox_rewrite", lambda evs: state.__setitem__("outbox", list(evs))), \
                mock.patch.object(track, "rejected_append", lambda ev, msg: state["rejected"].append(ev["id"])), \
                mock.patch.object(track, "normalise_event_lengths", lambda ev: ev):
            rc = track.cmd_flush(False)
        return rc, state

    def test_5xx_naming_an_event_keeps_the_outbox(self):
        rc, state = self.flush("server rejected 502: event 0: upstream")
        self.assertEqual((rc, state["rejected"], [e["id"] for e in state["outbox"]]), (2, [], ["a", "b"]))

    def test_auth_4xx_keeps_the_outbox(self):
        rc, state = self.flush("server rejected 401: event 0: bad token")
        self.assertEqual((rc, state["rejected"]), (2, []))


class TokenFile(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="worldtok.")
        self.path = Path(self.dir) / "token"
        self.path.write_text("tok-from-file\n")

    def token(self, mode, **env):
        os.chmod(self.path, mode)
        env.setdefault("WORLD_TOKEN_FILE", str(self.path))
        with mock.patch.dict(os.environ, env, clear=False):
            if "WORLD_TOKEN" not in env:
                os.environ.pop("WORLD_TOKEN", None)
            return lib_world.env_token()

    def test_private_file_is_read(self):
        self.assertEqual(self.token(0o600), "tok-from-file")

    def test_group_or_world_readable_file_is_refused(self):
        self.assertEqual(self.token(0o644), "")
        self.assertEqual(self.token(0o640), "")

    def test_env_wins_and_missing_file_is_empty(self):
        self.assertEqual(self.token(0o600, WORLD_TOKEN="from-env"), "from-env")
        self.assertEqual(self.token(0o600, WORLD_TOKEN_FILE=self.dir + "/nope"), "")

    def test_plist_has_the_file_path_and_no_token(self):
        plist = (HERE / "dev.mbardouni.world-push.plist").read_text()
        self.assertIn("<key>WORLD_TOKEN_FILE</key>", plist)
        self.assertNotIn("<key>WORLD_TOKEN</key>", plist)


class PrIds(unittest.TestCase):
    def collect(self, state, merged=False):
        pr = {"repository": {"nameWithOwner": "o/r"}, "number": 7, "state": state,
              "createdAt": "2026-10-01T00:00:00Z", "url": "u"}

        def fake_json(args, *a, **k):
            if "--merged" in args:
                return [pr] if merged else []
            return [pr]
        with mock.patch.object(wps, "_PENDING_STATE", {}), \
                mock.patch.object(wps, "STATE_DIR", Path(tempfile.mkdtemp(prefix="worldpr."))):
            def fake_run(cmd, *a, **k):
                return mock.Mock(returncode=0, stdout=__import__("json").dumps(fake_json(cmd)))
            with mock.patch.object(wps.subprocess, "run", fake_run):
                return list(wps.collect_prs())

    def test_state_change_gets_a_new_id(self):
        a = self.collect("open")
        b = self.collect("closed", merged=True)
        self.assertEqual((a[0]["kind"], b[0]["kind"]), ("pr", "merge"))
        self.assertNotEqual(a[0]["id"], b[0]["id"])
        self.assertEqual(self.collect("open")[0]["id"], a[0]["id"])  # same state, same id


class GitCursor(unittest.TestCase):
    def run_collect(self, log_result):
        repo = Path(tempfile.mkdtemp(prefix="worldgit."))
        pending = {}
        with mock.patch.object(wps, "iter_git_roots", lambda roots: [repo]), \
                mock.patch.object(wps, "_resolve_canonical_repo", lambda r: (repo, "p")), \
                mock.patch.object(wps, "_git_out", lambda r, a, t=20: "abc123\n"), \
                mock.patch.object(wps, "_git_log", lambda *a, **k: log_result), \
                mock.patch.object(wps, "_state_read", lambda p: "old999"), \
                mock.patch.object(wps, "_PENDING_STATE", pending):
            events = list(wps.collect_git(roots=[repo]))
        return events, pending

    def test_failed_git_log_does_not_advance_the_cursor(self):
        events, pending = self.run_collect(None)
        self.assertEqual((events, pending), ([], {}))

    def test_successful_log_advances_it(self):
        events, pending = self.run_collect([("abc123", "2026-10-01T00:00:00Z", "msg")])
        self.assertEqual(len(events), 1)
        self.assertEqual(list(pending.values()), ["abc123"])


if __name__ == "__main__":
    unittest.main()
