"""F5: jdelegate registers its worker in the SERVER registry over ssh (fake ssh here, no network): submit, run start/end, spool replay."""
import glob
import json
import os
import subprocess
import tempfile
import unittest

JDELEGATE = os.path.join(os.path.dirname(__file__), "..", "bin", "jdelegate")
PIN = "cliproxy/claude-haiku-5-5"

# Fake ssh HOST CMD...: logs the remote command line and its stdin; answers like the server's factory/frun.
SSH_STUB = r"""#!/bin/sh
while [ "$1" = -o ]; do shift 2; done
host=$1; shift
printf '%s\n' "$host $*" >> "$FAKE_SSH_LOG"
case "$*" in
  *"factory submit"*) cat > "$FAKE_SSH_LOG.brief"; echo "proj:owner:abc123:1"; exit 0;;
  *"frun start"*) echo "jdelegate:testmac:4242:1"; exit 0;;
  *"frun finish"*) [ -e "$FAKE_SSH_DOWN" ] && exit 255; exit 0;;
esac
exit 0
"""
CLAUDE_STUB = "#!/bin/sh\ncat >/dev/null\necho ok\n"


def write_exe(path, body):
    with open(path, "w") as f:
        f.write(body)
    os.chmod(path, 0o755)


GUARD = os.path.join(os.path.dirname(__file__), "fake-ssh-guard.sh")


def install_guard(test, tmpdir, env):
    """Spec 002 D2: a guard `ssh` is first on PATH (an explicit JDELEGATE_REG_SSH fake still works); teardown fails when it saw a real host."""
    d = os.path.join(tmpdir, "ssh-guard")
    os.makedirs(d)
    write_exe(os.path.join(d, "ssh"), open(GUARD).read())
    test.guard_log = os.path.join(tmpdir, "ssh-guard.log")
    env["SSH_GUARD_LOG"] = test.guard_log
    env["PATH"] = f"{d}:{env['PATH']}"


def assert_no_real_ssh(test):
    calls = open(test.guard_log).read().splitlines() if os.path.exists(test.guard_log) else []
    real = [c for c in calls if not c.startswith("fake-host ")]
    test.assertEqual(real, [], "a test reached ssh")


class RegisterTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = self.tmp.name
        self.repo = os.path.join(t, "repo")
        os.mkdir(self.repo)
        subprocess.run(["git", "init", "-q", self.repo], check=True)
        self.cache = os.path.join(t, "cache")
        self.log = os.path.join(t, "ssh.log")
        self.down = os.path.join(t, "ssh-down")
        self.bin = os.path.join(t, "bin")
        os.mkdir(self.bin)
        write_exe(os.path.join(self.bin, "ssh"), SSH_STUB)
        write_exe(os.path.join(self.bin, "claude"), CLAUDE_STUB)
        jev = os.path.join(t, "jev")
        write_exe(jev, "#!/bin/sh\nexit 1\n")
        env = {**os.environ, "JDELEGATE_JEV": jev, "JDELEGATE_CACHE": self.cache, "JDELEGATE_SELECT_CACHE": "0",
               "JDELEGATE_AUTO_MCP": "0", "JDELEGATE_AUTO_SKILL": "0", "WORLD_TRACK": "0",
               "JDELEGATE_REG_SSH": os.path.join(self.bin, "ssh"), "FAKE_SSH_LOG": self.log, "FAKE_SSH_DOWN": self.down,
               "PATH": f"{self.bin}:{os.environ['PATH']}"}
        for k in ("FACTORY_BIN", "FACTORY_JOB_ID", "HERDR_ENV", "HERDR_PANE_ID"):
            env.pop(k, None)
        self.env = env
        install_guard(self, t, self.env)

    def tearDown(self):
        assert_no_real_ssh(self)
        self.tmp.cleanup()

    def launch(self, *extra):
        return subprocess.run(["node", JDELEGATE, "--no-tab", "--no-auto-role", "--model", PIN, "--cwd", self.repo,
                               "--name", "f5-probe", "--timeout", "5", *extra, "reply ok"],
                              capture_output=True, text=True, env=self.env, timeout=120)

    def calls(self):
        return open(self.log).read().splitlines() if os.path.exists(self.log) else []

    def test_submit_start_end_go_to_the_server(self):
        r = self.launch()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        calls = self.calls()
        self.assertTrue(calls[0].startswith("MyContabo factory submit "), calls)
        self.assertIn("--brief - --owner", calls[0])
        self.assertIn("reply ok", open(self.log + ".brief").read())  # the brief rides on stdin
        start = next(c for c in calls if "frun start" in c)
        for part in ("--source jdelegate", "--name f5-probe", "--model claude-haiku-5-5", "--job proj:owner:abc123:1",
                     "--host ", "--pid ", "timeout=300"):
            self.assertIn(part, start)
        fin = next(c for c in calls if "frun finish" in c)
        self.assertIn("jdelegate:testmac:4242:1 0", fin)
        self.assertLess(calls.index(start), calls.index(fin))
        self.assertNotIn("launching unregistered", r.stderr)

    def test_failed_end_is_spooled_and_replayed_on_next_start(self):
        open(self.down, "w").close()
        r = self.launch()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        spool = glob.glob(os.path.join(self.cache, "reg-spool*"))
        self.assertEqual(len(spool), 1)
        lines = [json.loads(l) for l in open(spool[0]).read().splitlines() if l.strip()]
        self.assertEqual(len(lines), 1)
        self.assertIn("finish", lines[0]["args"])
        os.remove(self.down)
        open(self.log, "w").close()
        r = self.launch()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        calls = self.calls()
        replay = [i for i, c in enumerate(calls) if "frun finish" in c]
        self.assertEqual(len(replay), 2, calls)  # the replayed old end, then this run's own end
        self.assertLess(replay[0], next(i for i, c in enumerate(calls) if "factory submit" in c))
        self.assertEqual(open(spool[0]).read().strip(), "")

    def test_unreachable_server_only_warns(self):
        self.env["JDELEGATE_REG_SSH"] = "/nonexistent/ssh"
        r = self.launch()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("launching unregistered", r.stderr)

    def test_halted_project_exit_97(self):
        write_exe(os.path.join(self.bin, "ssh"), "#!/bin/sh\necho 'submit: halted' >&2\nexit 97\n")
        r = self.launch()
        self.assertEqual(r.returncode, 97, r.stdout + r.stderr)

    def test_tmp_cwd_without_explicit_fake_ssh_never_calls_ssh(self):  # T1: the tmp repo is throwaway work
        del self.env["JDELEGATE_REG_SSH"]
        r = self.launch()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.calls(), [])
        self.assertFalse(os.path.exists(self.guard_log))

    def test_registration_off_switch(self):  # T3
        del self.env["JDELEGATE_REG_SSH"]
        self.env["JDELEGATE_REG"] = "0"
        r = subprocess.run(["node", JDELEGATE, "--no-tab", "--no-auto-role", "--model", PIN, "--cwd", os.path.dirname(os.path.dirname(os.path.abspath(JDELEGATE))),
                            "--name", "f5-off", "--timeout", "5", "reply ok"], capture_output=True, text=True, env=self.env, timeout=120)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.calls(), [])


if __name__ == "__main__":
    unittest.main()
