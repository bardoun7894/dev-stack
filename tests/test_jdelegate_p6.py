"""P6.08: jdelegate --model pin, advisor only on retry, pay-per-token keys unset for the worker (no network: Jev stubbed, --dry-run).
P6.08b: the auto-routed chain skips refs without a jdelegate harness, kind language stays on its own chain (fake tiers + quota files, --print)."""
import datetime
import glob
import json
import os
import subprocess
import tempfile
import unittest

JDELEGATE = os.path.join(os.path.dirname(__file__), "..", "bin", "jdelegate")
PIN = "cliproxy/claude-haiku-5-5"

FACTORY_STUB = "#!/bin/sh\necho registering\necho job-1\n"
# Stands in for `claude`: prints the pay-per-token keys as the worker sees them.
CLAUDE_STUB = """#!/bin/sh
cat >/dev/null
for k in XAI_API_KEY GEMINI_API_KEY GOOGLE_API_KEY OPENAI_API_KEY OPENROUTER_API_KEY; do
  eval "v=\\${$k-<unset>}"
  echo "$k=$v"
done
"""


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


def route_stub(kind):
    """A `jev` that answers the routing question: tier T3, the given kind, doer."""
    answers = {"tier": {"choice": "T3", "confidence": 0.9}, "kind": {"choice": kind, "confidence": 0.9}, "role": {"choice": "doer", "confidence": 0.9}, "ui": {"noul": 0}}
    return "#!/bin/sh\ncat >/dev/null\necho '%s'\n" % json.dumps({"answers": answers})


class P6Test(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = self.tmp.name
        self.repo = os.path.join(t, "repo")
        os.mkdir(self.repo)
        subprocess.run(["git", "init", "-q", self.repo], check=True)
        self.cache = os.path.join(t, "cache")
        self.jev_calls = os.path.join(t, "jev-calls.txt")
        self.bin = os.path.join(t, "bin")
        os.mkdir(self.bin)
        write_exe(os.path.join(self.bin, "factory"), FACTORY_STUB)
        write_exe(os.path.join(self.bin, "claude"), CLAUDE_STUB)
        jev = os.path.join(t, "jev")  # records each call, then fails: jdelegate falls back to its safe default route
        write_exe(jev, f'#!/bin/sh\necho "$@" >> {self.jev_calls}\nexit 1\n')
        self.env = {
            **os.environ,
            "JDELEGATE_JEV": jev,
            "JDELEGATE_CACHE": self.cache,
            "JDELEGATE_SELECT_CACHE": "0",
            "JDELEGATE_AUTO_MCP": "0",
            "JDELEGATE_AUTO_SKILL": "0",
            "WORLD_TRACK": "0",
            "FACTORY_BIN": os.path.join(self.bin, "factory"),
        }
        for k in ("FACTORY_RETRY", "JDELEGATE_ADVISOR", "JDELEGATE_REG_SSH"):
            self.env.pop(k, None)
        install_guard(self, t, self.env)

    def tearDown(self):
        assert_no_real_ssh(self)
        self.tmp.cleanup()

    def dry(self, *args, **extra):
        return subprocess.run(
            ["node", JDELEGATE, "--dry-run", "--no-auto-role", "--cwd", self.repo, *args, "echo hi"],
            capture_output=True, text=True, env={**self.env, **extra}, timeout=60,
        )

    def test_no_advisor_on_first_attempt(self):
        r = self.dry("--model", PIN)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("claude -p --model 'claude-haiku-5-5'", r.stdout)
        self.assertNotIn("--advisor", r.stdout)

    def test_retry_adds_advisor_opus(self):
        self.assertNotIn("--advisor", self.dry("--model", PIN).stdout)
        for r in (self.dry("--model", PIN, "--retry"), self.dry("--model", PIN, FACTORY_RETRY="1")):
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("--advisor opus", r.stdout)
        off = self.dry("--model", PIN, "--retry", JDELEGATE_ADVISOR="0")
        self.assertEqual(off.returncode, 0, off.stderr)
        self.assertNotIn("--advisor", off.stdout)
        other = self.dry("--model", PIN, "--retry", JDELEGATE_ADVISOR="sonnet")
        self.assertIn("--advisor sonnet", other.stdout)

    def test_model_pin_skips_routing(self):
        r = self.dry("--model", "cliproxy/claude-sonnet-5-5")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("claude -p --model 'claude-sonnet-5-5'", r.stdout)
        self.assertIn("pinned", r.stdout)
        calls = open(self.jev_calls).read() if os.path.exists(self.jev_calls) else ""
        self.assertNotIn("router-delegate", calls)  # no routing question reached Jev

    def test_model_pin_rejects_openrouter_and_openai(self):
        for ref in ("openrouter/anthropic/claude-haiku-5-5", "openai-codex/gpt-5.5", "openai/gpt-5.5", "nosuchprovider/x", "claude-haiku-5-5", ""):
            r = self.dry("--model", ref)
            self.assertEqual(r.returncode, 2, (ref, r.stdout, r.stderr))
            self.assertIn("D0", r.stderr)
            self.assertEqual(glob.glob(os.path.join(self.cache, "*", "run.sh")), [], ref)
        for ref in ("opencode-go/deepseek-v4.1-flash", "agy/gemini-4-argon-high"):
            self.assertEqual(self.dry("--model", ref).returncode, 0, ref)

    def test_model_pin_rejects_foreign_harness(self):
        for harness in ("codex", "opencode", "pi", "agy"):
            r = self.dry("--model", PIN, "--harness", harness)
            self.assertEqual(r.returncode, 2, (harness, r.stdout, r.stderr))
            self.assertIn("--harness", r.stderr)
            self.assertNotIn("codex exec", r.stdout)
            self.assertEqual(glob.glob(os.path.join(self.cache, "*", "run.sh")), [], harness)
        same = self.dry("--model", PIN, "--harness", "claude")
        self.assertEqual(same.returncode, 0, same.stderr)
        self.assertIn("claude -p --model 'claude-haiku-5-5'", same.stdout)

    def test_model_pin_without_jdelegate_harness_exit_2(self):
        for ref in ("xai/grok-4.7", "gemini/gemini-3.8-flash", "commandcode/glm-5.3-flash"):
            r = self.dry("--model", ref)
            self.assertEqual(r.returncode, 2, (ref, r.stdout, r.stderr))
            self.assertIn("server-agent.sh", r.stderr)
            self.assertEqual(glob.glob(os.path.join(self.cache, "*", "run.sh")), [], ref)

    def test_pay_per_token_keys_unset_openrouter_key_kept_for_jev(self):
        keys = {k: f"sk-{k}" for k in ("XAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENAI_API_KEY", "OPENROUTER_API_KEY")}
        r = self.dry("--model", PIN, **keys)
        self.assertEqual(r.returncode, 0, r.stderr)
        run_sh = glob.glob(os.path.join(self.cache, "*", "run.sh"))[0]
        out = subprocess.run(["bash", run_sh], capture_output=True, text=True, env={**self.env, **keys, "PATH": f"{self.bin}:{os.environ['PATH']}"}, timeout=60)
        for k in ("XAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENAI_API_KEY"):
            self.assertIn(f"{k}=<unset>", out.stdout, out.stdout + out.stderr)
        self.assertIn("OPENROUTER_API_KEY=sk-OPENROUTER_API_KEY", out.stdout)


    def route(self, kind, tiers, quota=None, exhausted=None, *args):
        t = self.tmp.name
        write_exe(os.path.join(t, "jev"), route_stub(kind))
        tiers_file = os.path.join(t, "tiers.json")
        extra = {"JEV_ROUTER_CONFIG": tiers_file, "JEV_EXHAUSTED_FILE": os.path.join(t, "exhausted.json")}
        with open(tiers_file, "w") as f:
            json.dump(tiers, f)
        with open(extra["JEV_EXHAUSTED_FILE"], "w") as f:
            json.dump(exhausted or {}, f)
        if quota is not None:
            extra["JEV_QUOTA_FILE"] = os.path.join(t, "quota.json")
            with open(extra["JEV_QUOTA_FILE"], "w") as f:
                json.dump({"at": datetime.datetime.now(datetime.timezone.utc).isoformat(), "providers": quota}, f)
        return subprocess.run(
            ["node", JDELEGATE, "--print", "--no-auto-role", "--cwd", self.repo, *args, "echo hi"],
            capture_output=True, text=True, env={**self.env, **extra}, timeout=60,
        )

    def test_auto_chain_skips_refs_without_harness(self):
        tiers = {
            "quota_policy": {"warm": 0.7, "hot": 0.9, "stale_minutes": 20},
            "kinds": {"code": {"T3": ["xai/test-grok", "gemini/test-gem", "commandcode/test-cc", "cliproxy/test-claude"]}},
        }
        hot = {"cliproxy": {"five_hour": 0.97}}  # hot quota ranks cliproxy last; unranked xai/gemini would win
        r = self.route("code", tiers, hot)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("claude · cliproxy/test-claude", r.stdout)
        for ref in ("xai/", "gemini/", "commandcode/"):
            self.assertNotIn(ref, r.stdout)
        skipped = [ln for ln in r.stderr.splitlines() if "server-agent.sh" in ln]
        self.assertEqual(len(skipped), 1, r.stderr)
        for ref in ("xai/test-grok", "gemini/test-gem", "commandcode/test-cc"):
            self.assertIn(ref, skipped[0])
        # nothing launchable left: no live model, exit 1
        none = self.route("code", {"kinds": {"code": {"T3": ["xai/test-grok"]}}}, None)
        self.assertEqual(none.returncode, 1, none.stdout + none.stderr)
        self.assertIn("no live model", none.stdout)

    def test_language_chain_no_tiers_append(self):
        tiers = {
            "kinds": {"language": {"T3": ["cliproxy/test-claude"]}, "code": {"T3": ["cliproxy/test-claude"]}},
            "tiers": {"T3": ["opencode-go/test-oc"]},
        }
        gone = {"cliproxy": 4102444800000}  # cliproxy exhausted: only tiers.* is left
        lang = self.route("language", tiers, None, gone)
        self.assertEqual(lang.returncode, 1, lang.stdout + lang.stderr)
        self.assertIn("no live model", lang.stdout)
        self.assertNotIn("opencode-go", lang.stdout)
        code = self.route("code", tiers, None, gone)  # other kinds still fall through to tiers.*
        self.assertEqual(code.returncode, 0, code.stdout + code.stderr)
        self.assertIn("opencode-go/test-oc", code.stdout)

    def test_language_exempt_provider_kept_under_hot_quota(self):
        tiers = {
            "quota_policy": {"warm": 0.7, "hot": 0.9, "stale_minutes": 20, "exempt": {"language": ["cliproxy"]}},
            "kinds": {"language": {"T3": ["cliproxy/test-claude", "opencode-go/test-oc"]}},
        }
        hot = {"cliproxy": {"five_hour": 0.99}}
        kept = self.route("language", tiers, hot)
        self.assertEqual(kept.returncode, 0, kept.stdout + kept.stderr)
        self.assertIn("cliproxy/test-claude", kept.stdout)
        self.assertNotIn("demoted", kept.stdout)
        del tiers["quota_policy"]["exempt"]  # control: without the exemption hot quota demotes it
        demoted = self.route("language", tiers, hot)
        self.assertIn("opencode-go/test-oc", demoted.stdout)
        tiers["quota_policy"]["exempt"] = {"test": ["cliproxy"]}  # an exemption for another kind does not apply
        other = self.route("language", tiers, hot)
        self.assertIn("opencode-go/test-oc", other.stdout)


if __name__ == "__main__":
    unittest.main()
