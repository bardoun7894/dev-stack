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


if __name__ == "__main__":
    unittest.main()
