"""Tests for scripts/gen-worker-skills.py: a Jev failure or timeout leaves the skill out (fail closed)."""
import importlib.machinery
import importlib.util
import os
import subprocess
import unittest
from unittest import mock

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
loader = importlib.machinery.SourceFileLoader("gen_worker_skills", os.path.join(ROOT, "scripts", "gen-worker-skills.py"))
spec = importlib.util.spec_from_loader(loader.name, loader)
gen = importlib.util.module_from_spec(spec)
loader.exec_module(gen)


class ClassifyTest(unittest.TestCase):
    def test_timeout_for_one_skill_is_an_error_verdict_not_a_crash(self):
        def run(cmd, **kw):
            if "slow: d" in cmd[cmd.index("-s") + 1]:
                raise subprocess.TimeoutExpired(cmd, 30)
            return subprocess.CompletedProcess(cmd, 0, stdout="worker\n", stderr="")

        with mock.patch.object(gen.subprocess, "run", side_effect=run):
            self.assertEqual(gen.classify(("slow", "d")), ("slow", "error"))
            self.assertEqual(gen.classify(("fast", "d")), ("fast", "worker"))

    def test_a_timeout_does_not_drop_the_other_skills(self):
        def run(cmd, **kw):
            if "slow: d" in cmd[cmd.index("-s") + 1]:
                raise subprocess.TimeoutExpired(cmd, 30)
            return subprocess.CompletedProcess(cmd, 0, stdout="both\n", stderr="")

        with mock.patch.object(gen.subprocess, "run", side_effect=run):
            got = dict(map(gen.classify, {"slow": "d", "fast": "d"}.items()))
        self.assertEqual(got, {"slow": "error", "fast": "both"})


if __name__ == "__main__":
    unittest.main()
