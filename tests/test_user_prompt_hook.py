"""Tests for hooks/user-prompt-kb-check.sh: once-per-session blocks, skip rules and Jev call count (suggest stubbed)."""
import json
import os
import subprocess
import tempfile
import unittest

HOOK = os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "hooks", "user-prompt-kb-check.sh")


class HookTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = os.path.realpath(self.tmp.name)
        os.makedirs(os.path.join(self.home, ".claude"))
        with open(os.path.join(self.home, ".claude", ".dev-stack-health"), "w") as f:
            f.write("OK\n")
        with open(os.path.join(self.home, ".claude", ".rule-drift-cache"), "w") as f:
            f.write("DRIFT: 2 skills added\n")
        self.proj = os.path.join(self.home, "proj")
        os.makedirs(os.path.join(self.proj, ".git"))
        os.makedirs(os.path.join(self.proj, "ai-knowledge-base", "scripts"))
        open(os.path.join(self.proj, "ai-knowledge-base", "scripts", "query.py"), "w").close()
        os.makedirs(os.path.join(self.proj, ".specify", "templates"))
        open(os.path.join(self.proj, ".specify", "templates", "spec-template.md"), "w").close()
        self.counter = os.path.join(self.home, "suggest-calls")
        self.stub = os.path.join(self.home, "suggest-stub")
        with open(self.stub, "w") as f:
            f.write("import sys\nopen(%r, 'a').write('x')\nsys.stdin.read()\n"
                    "print('<skill_relevance>Relevant to the current request: stubskill.</skill_relevance>')\n"
                    % self.counter)

    fakebin = None

    def no_kb_and_jev_says_not_engineering(self):
        """Drop the KB strong signal and stub `jev noul` to exit 1, so a vocabulary miss is a skip."""
        os.remove(os.path.join(self.proj, "ai-knowledge-base", "scripts", "query.py"))
        self.fakebin = os.path.join(self.home, "fakebin")
        os.makedirs(self.fakebin)
        with open(os.path.join(self.fakebin, "jev"), "w") as f:
            f.write("#!/bin/sh\nexit 1\n")
        os.chmod(os.path.join(self.fakebin, "jev"), 0o755)

    def tearDown(self):
        self.tmp.cleanup()

    def run_hook(self, prompt, session="s1"):
        env = {"HOME": self.home, "PATH": (self.fakebin + ":" if self.fakebin else "") + os.environ["PATH"],
               "DEVSTACK_SUGGEST_BIN": self.stub}
        payload = {"prompt": prompt, "cwd": self.proj}
        if session:
            payload["session_id"] = session
        p = subprocess.run(["bash", HOOK], input=json.dumps(payload), capture_output=True, text=True,
                           cwd=self.proj, env=env, timeout=20)
        return p.stdout

    def calls(self):
        return len(open(self.counter).read()) if os.path.exists(self.counter) else 0

    def test_reminder_and_nag_print_once_per_session(self):
        first = self.run_hook("fix the login bug in the payment API", "sess-a")
        self.assertIn("REMINDER", first)
        self.assertIn("RULE OUT OF DATE", first)
        second = self.run_hook("now fix the other bug in the billing API", "sess-a")
        self.assertNotIn("REMINDER", second)
        self.assertNotIn("RULE OUT OF DATE", second)

    def test_trivial_first_prompt_does_not_use_up_the_reminder(self):
        self.no_kb_and_jev_says_not_engineering()
        first = self.run_hook("hello there", "sess-t")
        self.assertNotIn("REMINDER", first)
        self.assertIn("RULE OUT OF DATE", first)  # printed, so used up
        second = self.run_hook("fix the login bug in the payment API", "sess-t")
        self.assertIn("REMINDER", second)
        self.assertNotIn("RULE OUT OF DATE", second)
        third = self.run_hook("fix the other bug in the billing API", "sess-t")
        self.assertNotIn("REMINDER", third)
        self.assertNotIn("RULE OUT OF DATE", third)

    def test_markers_are_separate_lines_written_only_when_printed(self):
        self.no_kb_and_jev_says_not_engineering()
        marker = os.path.join(self.home, ".cache", "dev-stack", "hook-seen", "sess-m")
        self.run_hook("hello there", "sess-m")
        self.assertNotIn("reminded", open(marker).read().split("\n") if os.path.exists(marker) else [])
        self.run_hook("fix the login bug in the payment API", "sess-m")
        lines = open(marker).read().split("\n")
        self.assertIn("reminded", lines)
        self.assertIn("nagged", lines)

    def test_new_session_prints_again(self):
        self.run_hook("fix the login bug in the payment API", "sess-a")
        other = self.run_hook("fix the login bug in the payment API", "sess-b")
        self.assertIn("REMINDER", other)
        self.assertIn("RULE OUT OF DATE", other)

    def test_incomplete_warning_keeps_printing(self):
        with open(os.path.join(self.home, ".claude", ".dev-stack-health"), "w") as f:
            f.write("MISSING\n")
        self.run_hook("fix the login bug in the payment API", "sess-a")
        again = self.run_hook("fix the other bug in the billing API", "sess-a")
        self.assertIn("DEV-STACK INCOMPLETE", again)

    def test_repeat_turn_is_tiny(self):
        self.run_hook("fix the login bug in the payment API", "sess-a")
        again = self.run_hook("ok continue", "sess-a")
        self.assertLessEqual(len(again.encode()), 200)

    def test_old_markers_are_cleaned(self):
        seen = os.path.join(self.home, ".cache", "dev-stack", "hook-seen")
        os.makedirs(seen)
        old = os.path.join(seen, "ancient")
        open(old, "w").close()
        past = os.path.getmtime(old) - 3 * 86400
        os.utime(old, (past, past))
        self.run_hook("fix the login bug in the payment API", "sess-a")
        self.assertFalse(os.path.exists(old))

    def test_ack_and_short_prompts_make_no_jev_call(self):
        for p in ("ok continue", "yes", "continue", "go", "?", "نعم", "كمل", "oui", "d'accord",
                  "fix this please", "/kb-query something about the thing"):
            self.run_hook(p, "sess-skip")
        self.assertEqual(self.calls(), 0)

    def test_real_prompt_calls_suggest_once_per_session_and_skill(self):
        out = self.run_hook("fix the login bug in the payment API and add tests", "sess-c")
        self.assertIn("skill_relevance", out)
        self.assertEqual(self.calls(), 1)

    def test_no_session_id_still_works(self):
        out = self.run_hook("fix the login bug in the payment API", None)
        self.assertIn("REMINDER", out)

    def run_proc(self, prompt, session="s-kb", extra_env=None):
        env = {"HOME": self.home, "PATH": os.environ["PATH"], "DEVSTACK_SUGGEST_BIN": self.stub}
        env.update(extra_env or {})
        payload = {"prompt": prompt, "cwd": self.proj, "session_id": session}
        return subprocess.run(["bash", HOOK], input=json.dumps(payload), capture_output=True, text=True,
                              cwd=self.proj, env=env, timeout=20)

    def context(self, proc):
        return json.loads(proc.stdout)["hookSpecificOutput"]["additionalContext"] if proc.stdout.strip() else ""

    def write_kb_page(self, rel, title, body):
        path = os.path.join(self.proj, "ai-knowledge-base", "knowledge", rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"---\ntitle: {title}\n---\n{body}\n")

    def test_kb_prior_art_is_injected_as_json(self):
        self.write_kb_page("concepts/invoice-extraction.md", "Invoice extraction",
                           "Gemini extracts invoice pages; retry on timeout.")
        p = self.run_proc("how did we fix the invoice extraction")
        self.assertEqual(p.returncode, 0, p.stderr)
        ctx = self.context(p)
        self.assertIn("KB prior art (auto-retrieved; cite [[links]] when relevant):", ctx)
        self.assertIn("### [[invoice-extraction]]", ctx)
        self.assertIn("REMINDER", ctx)  # existing output is kept

    def test_no_kb_means_no_prior_art_block(self):
        p = self.run_proc("how did we fix the invoice extraction")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertNotIn("KB prior art", self.context(p))

    def test_prompts_under_three_words_are_skipped(self):
        self.write_kb_page("concepts/invoice-extraction.md", "Invoice extraction",
                           "Gemini extracts invoice pages; retry on timeout.")
        p = self.run_proc("invoice extraction")
        self.assertNotIn("KB prior art", self.context(p))

    def test_system_notifications_get_no_prior_art(self):
        self.write_kb_page("concepts/invoice-extraction.md", "Invoice extraction",
                           "Gemini extracts invoice pages; retry on timeout.")
        ask = "how did we fix the invoice extraction"
        self.assertIn("KB prior art", self.context(self.run_proc(ask, "s-n0")))  # control: same words, real prompt
        for i, prompt in enumerate((
                f"<task-notification><task-id>b1</task-id><summary>{ask}</summary></task-notification>",
                f"{ask} [SYSTEM NOTIFICATION: background task finished]",
                f"Heads up\n[SYSTEM NOTIFICATION] {ask}")):
            p = self.run_proc(prompt, f"s-n{i + 1}")
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertNotIn("KB prior art", self.context(p), prompt)

    def test_failing_kb_retrieve_never_fails_the_hook(self):
        self.write_kb_page("concepts/invoice-extraction.md", "Invoice extraction",
                           "Gemini extracts invoice pages; retry on timeout.")
        p = self.run_proc("how did we fix the invoice extraction", "s-kb-fail",
                          {"DEVSTACK_KB_RETRIEVE_BIN": "/nonexistent/kb-retrieve"})
        self.assertEqual(p.returncode, 0, p.stderr)
        ctx = self.context(p)
        self.assertNotIn("KB prior art", ctx)
        self.assertIn("REMINDER", ctx)


    def test_system_ux_auto_hint_fires_once_for_ui_ux_and_skips_backend(self):
        be = self.run_hook("fix the login bug in the payment API", "sess-ux-be")
        self.assertNotIn("AUTO-USE system-ux", be)

        first = self.run_hook("build an admin dashboard with filters for orders", "sess-ux-en")
        self.assertIn("AUTO-USE system-ux", first)
        second = self.run_hook("now add a multi-step onboarding form", "sess-ux-en")
        self.assertNotIn("AUTO-USE system-ux", second)

        ar = self.run_hook("صمم تجربة المستخدم ولوحة التحكم للطلبات", "sess-ux-ar")
        self.assertIn("AUTO-USE system-ux", ar)

if __name__ == "__main__":
    unittest.main()
