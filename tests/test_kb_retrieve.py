"""Tests for bin/kb-retrieve: local KB search for prior art, no AI call, empty output when nothing scores."""
import os
import subprocess
import tempfile
import time
import unittest

KB_RETRIEVE = os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "bin", "kb-retrieve")


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def page(title, body):
    return f"---\ntitle: {title}\n---\n{body}\n"


class KbRetrieveTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = os.path.realpath(self.tmp.name)
        self.home = os.path.join(self.base, "home")
        os.makedirs(self.home)
        self.proj = os.path.join(self.home, "proj")
        os.makedirs(os.path.join(self.proj, ".git"))
        self.kb = os.path.join(self.proj, "ai-knowledge-base", "knowledge")

    def tearDown(self):
        self.tmp.cleanup()

    def run_kb(self, *args, root=None, env_extra=None):
        env = dict(os.environ, HOME=self.home, KB_JEV="0", KB_GLOBAL_ROOTS=os.path.join(self.base, "no-global"))
        env.update(env_extra or {})
        cmd = ["python3", KB_RETRIEVE]
        if root is not None:
            cmd += ["--root", root]
        cmd += list(args)
        return subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=10)

    def test_title_hits_rank_first_and_output_format(self):
        write(os.path.join(self.kb, "concepts", "invoice-extraction.md"),
              page("Invoice extraction with Gemini", "We parse PDF invoices using Gemini vision."))
        write(os.path.join(self.kb, "concepts", "other.md"),
              page("Billing notes", "invoice numbers and gemini quotas are tracked here."))
        r = self.run_kb("invoice extraction gemini", root=self.proj)
        self.assertEqual(r.returncode, 0, r.stderr)
        first = r.stdout.split("\n", 1)[0]
        self.assertEqual(
            first,
            "### [[invoice-extraction]] (ai-knowledge-base/knowledge/concepts/invoice-extraction.md)")
        self.assertIn("parse PDF invoices", r.stdout)
        self.assertNotIn("title: Invoice", r.stdout)

    def test_single_body_hit_is_below_threshold(self):
        write(os.path.join(self.kb, "concepts", "misc.md"), page("Misc", "mentions invoice once"))
        r = self.run_kb("invoice", root=self.proj)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, "")

    def test_no_kb_prints_nothing_and_exits_zero(self):
        empty = os.path.join(self.base, "empty-proj")
        os.makedirs(os.path.join(empty, ".git"))
        r = self.run_kb("invoice extraction gemini", root=empty)
        self.assertEqual((r.returncode, r.stdout), (0, ""))

    def test_index_and_log_are_skipped(self):
        write(os.path.join(self.kb, "index.md"), page("Index", "invoice extraction gemini"))
        write(os.path.join(self.kb, "log.md"), page("Log", "invoice extraction gemini"))
        r = self.run_kb("invoice extraction gemini", root=self.proj)
        self.assertEqual((r.returncode, r.stdout), (0, ""))

    def test_okf_directory_is_searched(self):
        write(os.path.join(self.proj, "okf", "notes", "gemini-pricing.md"),
              page("Gemini pricing", "Token prices for gemini models."))
        r = self.run_kb("gemini pricing", root=self.proj)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("### [[gemini-pricing]] (okf/notes/gemini-pricing.md)", r.stdout)

    def test_k_and_max_chars_are_honoured(self):
        for i in range(5):
            write(os.path.join(self.kb, "concepts", f"deploy-note-{i}.md"),
                  page(f"Deploy note {i}", "deploy pipeline steps " * 80))
        r = self.run_kb("--k", "2", "deploy pipeline", root=self.proj)
        self.assertEqual(r.stdout.count("### [["), 2)
        r = self.run_kb("--max-chars", "300", "deploy pipeline", root=self.proj)
        self.assertLessEqual(len(r.stdout), 300)
        self.assertGreater(len(r.stdout), 0)

    def test_excerpt_is_capped_at_700_chars(self):
        write(os.path.join(self.kb, "concepts", "long.md"),
              page("Long page", "zebra giraffe " * 300))
        r = self.run_kb("zebra giraffe", root=self.proj)
        self.assertEqual(r.returncode, 0, r.stderr)
        body = r.stdout.split("\n", 1)[1]
        self.assertLessEqual(len(body.strip()), 700)

    def test_stopwords_only_query_prints_nothing(self):
        write(os.path.join(self.kb, "concepts", "the.md"), page("The and for", "the and for with"))
        r = self.run_kb("the and for with", root=self.proj)
        self.assertEqual((r.returncode, r.stdout), (0, ""))

    def test_arabic_terms_are_kept(self):
        write(os.path.join(self.kb, "concepts", "fawatir.md"),
              page("استخراج الفواتير", "نستخرج الفواتير من الصور باستخدام نموذج."))
        r = self.run_kb("كيف تم استخراج الفواتير", root=self.proj)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("### [[fawatir]]", r.stdout)

    def test_arabic_hamza_variants_match_in_content(self):
        write(os.path.join(self.kb, "concepts", "recovery.md"),
              page("معالجة الدفعة", "نعيد إصلاح خطأ الفاتورة بعد الفشل."))
        r = self.run_kb("إصلاح خطأ", root=self.proj)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("### [[recovery]]", r.stdout)

    def test_filename_only_match_is_kept(self):
        write(os.path.join(self.kb, "concepts", "gemini-pricing.md"), "Token prices for models.\n")
        r = self.run_kb("gemini pricing", root=self.proj)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("### [[gemini-pricing]]", r.stdout)

    def test_root_is_found_by_walking_up_to_git_marker(self):
        write(os.path.join(self.kb, "concepts", "invoice-extraction.md"),
              page("Invoice extraction", "invoice extraction gemini details"))
        deep = os.path.join(self.proj, "src", "deep")
        os.makedirs(deep)
        r = self.run_kb("invoice extraction gemini", root=deep)
        self.assertIn("### [[invoice-extraction]]", r.stdout)

    def test_marker_above_home_is_never_used(self):
        outside = self.base
        os.makedirs(os.path.join(outside, ".git"), exist_ok=True)
        write(os.path.join(outside, "ai-knowledge-base", "knowledge", "concepts", "leak.md"),
              page("Leak", "invoice extraction gemini"))
        sub = os.path.join(self.home, "sub")
        os.makedirs(sub)
        r = self.run_kb("invoice extraction gemini", root=sub)
        self.assertEqual((r.returncode, r.stdout), (0, ""))

    def test_200_file_kb_under_half_second(self):
        for i in range(200):
            write(os.path.join(self.kb, "concepts", f"topic-{i}.md"),
                  page(f"Topic {i}", "lorem ipsum dolor sit amet " * 40 + f" invoice gemini {i}"))
        started = time.monotonic()
        r = self.run_kb("invoice extraction gemini", root=self.proj)
        elapsed = time.monotonic() - started
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertLess(elapsed, 0.5)


FAKE_JEV = """#!/usr/bin/env python3
import json, os, sys
mode = os.environ.get("FAKE_JEV_MODE", "")
if mode == "exit3":
    sys.stderr.write("jev: HTTP 500\\n"); sys.exit(3)
if mode == "sleep":
    import time; time.sleep(10)
req = json.load(sys.stdin)
open(os.environ["FAKE_JEV_SEEN"], "a").write(json.dumps({"argv": sys.argv[1:], "req": req}) + "\\n")
drop = [x for x in os.environ.get("FAKE_JEV_UNRELATED", "").split(",") if x]
answers = {}
for qid in req["questions"]:
    lvl = 0 if qid in drop else 2
    answers[qid] = {"type": "score", "score": float(lvl),
                    "legend": {"0": "unrelated", "1": "weak", "2": "relevant", "3": "directly answers"},
                    "probabilities": {str(i): float(i == lvl) for i in range(4)}, "confidence": 1}
print(json.dumps({"model": "typesafe/jev-1.13", "answers": answers, "usage": {"input_tokens": 1, "output_tokens": 1, "cost": 0}, "id": "gen-dec-x", "provider": "TypeSafe"}))
"""

FAKE_CLAUDE = """#!/usr/bin/env bash
cat > "$FAKE_CLAUDE_STDIN"
echo "$@" > "$FAKE_CLAUDE_ARGS"
if [ "$FAKE_CLAUDE_MODE" = fail ]; then echo boom >&2; exit 1; fi
echo "BRIEF [[invoice-extraction]] retry on timeout"
"""


class KbRetrieveJevCondenseTest(unittest.TestCase):
    """Same fixtures, with fake jev / claude binaries first on PATH."""

    setUp_base = KbRetrieveTest.setUp
    tearDown = KbRetrieveTest.tearDown

    def setUp(self):
        self.setUp_base()
        self.bindir = os.path.join(self.base, "bin")
        self.seen = os.path.join(self.base, "jev-seen.jsonl")
        self.cl_stdin = os.path.join(self.base, "claude-stdin.txt")
        self.cl_args = os.path.join(self.base, "claude-args.txt")
        for name, body in (("jev", FAKE_JEV), ("claude", FAKE_CLAUDE)):
            path = os.path.join(self.bindir, name)
            write(path, body)
            os.chmod(path, 0o755)
        write(os.path.join(self.kb, "concepts", "invoice-extraction.md"),
              page("Invoice extraction", "Gemini extracts invoice pages; retry on timeout."))
        write(os.path.join(self.kb, "concepts", "invoice-numbering.md"),
              page("Invoice numbering", "Invoice extraction numbers are sequential per year."))

    def run_kb(self, *args, root=None, env_extra=None):
        env = {"PATH": self.bindir + os.pathsep + os.environ["PATH"], "KB_JEV": "1", "FAKE_JEV_SEEN": self.seen,
               "FAKE_CLAUDE_STDIN": self.cl_stdin, "FAKE_CLAUDE_ARGS": self.cl_args}
        env.update(env_extra or {})
        return KbRetrieveTest.run_kb(self, *args, root=root or self.proj, env_extra=env)

    def jev_calls(self):
        if not os.path.exists(self.seen):
            return []
        with open(self.seen) as f:
            return [__import__("json").loads(line) for line in f if line.strip()]

    def test_jev_keeps_relevant_in_one_call_and_logs_tag(self):
        r = self.run_kb("invoice extraction")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("[[invoice-extraction]]", r.stdout)
        self.assertIn("[[invoice-numbering]]", r.stdout)
        calls = self.jev_calls()
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["argv"], ["raw", "--log", "kb-retrieve"])
        req = calls[0]["req"]
        self.assertEqual(req["state"]["prompt"], "invoice extraction")
        self.assertEqual({a["id"] for a in req["state"]["articles"]}, set(req["questions"]))
        self.assertEqual(req["questions"]["invoice-extraction"]["criteria"],
                         ["unrelated", "weak", "relevant", "directly answers"])
        art = [a for a in req["state"]["articles"] if a["id"] == "invoice-extraction"][0]
        self.assertEqual(art["title"], "Invoice extraction")
        self.assertIn("retry on timeout", art["head"])

    def test_jev_drops_unrelated(self):
        r = self.run_kb("invoice extraction", env_extra={"FAKE_JEV_UNRELATED": "invoice-numbering"})
        self.assertIn("[[invoice-extraction]]", r.stdout)
        self.assertNotIn("[[invoice-numbering]]", r.stdout)

    def test_jev_keeping_nothing_prints_nothing(self):
        r = self.run_kb("invoice extraction",
                        env_extra={"FAKE_JEV_UNRELATED": "invoice-extraction,invoice-numbering"})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, "")

    def test_jev_exit_3_falls_back_to_keyword_top_k(self):
        r = self.run_kb("invoice extraction", "--k", "1", env_extra={"FAKE_JEV_MODE": "exit3"})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.count("### [["), 1)
        self.assertIn("[[invoice-extraction]]", r.stdout)

    def test_jev_timeout_falls_back_to_keyword(self):
        started = time.monotonic()
        r = self.run_kb("invoice extraction", env_extra={"FAKE_JEV_MODE": "sleep"})
        self.assertLess(time.monotonic() - started, 5)
        self.assertIn("[[invoice-extraction]]", r.stdout)

    def test_no_jev_flag_and_env_skip_the_call(self):
        self.run_kb("--no-jev", "invoice extraction")
        self.run_kb("invoice extraction", env_extra={"KB_JEV": "0"})
        self.assertEqual(self.jev_calls(), [])

    def test_condense_prints_haiku_result_with_lean_flags(self):
        r = self.run_kb("--condense", "invoice extraction")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "BRIEF [[invoice-extraction]] retry on timeout")
        with open(self.cl_args) as f:
            args = f.read()
        self.assertIn("-p --model haiku", args)
        self.assertIn("disableAllHooks", args)
        self.assertIn("--strict-mcp-config", args)
        with open(self.cl_stdin) as f:
            sent = f.read()
        self.assertIn("invoice extraction", sent)
        self.assertIn("[[invoice-extraction]]", sent)

    def test_condense_failure_prints_uncondensed_output(self):
        r = self.run_kb("--condense", "invoice extraction", env_extra={"FAKE_CLAUDE_MODE": "fail"})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("### [[invoice-extraction]]", r.stdout)
        self.assertNotIn("BRIEF", r.stdout)

    def test_condense_not_called_without_output(self):
        r = self.run_kb("--condense", "zzzunmatched qqqterm")
        self.assertEqual(r.stdout, "")
        self.assertFalse(os.path.exists(self.cl_stdin))


class KbRetrieveGlobalTest(unittest.TestCase):
    """Cross-project fallback: cached index over KB_GLOBAL_ROOTS, fake jev, fake background rebuild."""

    setUp_base = KbRetrieveTest.setUp
    tearDown = KbRetrieveTest.tearDown

    def setUp(self):
        self.setUp_base()
        self.groot = os.path.join(self.base, "groot")
        self.other = os.path.join(self.groot, "abd")
        write(os.path.join(self.other, "ai-knowledge-base", "knowledge", "concepts", "invoice-extraction.md"),
              page("Invoice extraction", "Gemini extracts invoice pages; retry on timeout."))
        self.nokb = os.path.join(self.base, "nokb")
        os.makedirs(os.path.join(self.nokb, ".git"))
        self.index = os.path.join(self.home, ".cache", "kb-retrieve", "global-index.json")

    def run_kb(self, *args, root=None, env_extra=None):
        env = {"KB_GLOBAL_ROOTS": self.groot}
        env.update(env_extra or {})
        return KbRetrieveTest.run_kb(self, *args, root=root or self.nokb, env_extra=env)

    def test_no_kb_root_hits_global_with_project_label(self):
        r = self.run_kb("invoice extraction gemini")
        self.assertEqual(r.returncode, 0, r.stderr)
        first = r.stdout.split("\n", 1)[0]
        self.assertEqual(first, "### [[abd/invoice-extraction]] (%s)" % os.path.join(
            self.other, "ai-knowledge-base", "knowledge", "concepts", "invoice-extraction.md"))
        self.assertIn("Gemini extracts invoice pages", r.stdout)
        self.assertTrue(os.path.exists(self.index))

    def test_local_miss_falls_back_to_global(self):
        write(os.path.join(self.kb, "concepts", "unrelated.md"), page("Deploy notes", "nginx and systemd only"))
        r = self.run_kb("invoice extraction gemini", root=self.proj)
        self.assertIn("### [[abd/invoice-extraction]]", r.stdout)

    def test_local_hit_stays_local(self):
        write(os.path.join(self.kb, "concepts", "invoice-extraction.md"),
              page("Invoice extraction", "local copy of the invoice extraction notes with gemini"))
        r = self.run_kb("invoice extraction gemini", root=self.proj)
        self.assertTrue(r.stdout.startswith("### [[invoice-extraction]] (ai-knowledge-base/"), r.stdout)
        self.assertNotIn("abd/", r.stdout)

    def test_current_root_is_not_searched_globally(self):
        r = self.run_kb("invoice extraction gemini", root=self.other)
        self.assertTrue(r.stdout.startswith("### [[invoice-extraction]] (ai-knowledge-base/"), r.stdout)
        self.assertNotIn("abd/invoice", r.stdout)

    def test_worktree_is_skipped(self):
        wt = os.path.join(self.groot, "abd-wt")
        write(os.path.join(wt, ".git"), "gitdir: /elsewhere\n")
        write(os.path.join(wt, "ai-knowledge-base", "knowledge", "wt-only-invoice.md"),
              page("Worktree invoice extraction gemini", "invoice extraction gemini worktree copy"))
        r = self.run_kb("invoice extraction gemini worktree", env_extra={})
        self.assertNotIn("abd-wt", r.stdout)
        self.assertIn("[[abd/invoice-extraction]]", r.stdout)

    def test_kb_global_zero_and_flag_disable(self):
        r = self.run_kb("invoice extraction gemini", env_extra={"KB_GLOBAL": "0"})
        self.assertEqual((r.returncode, r.stdout), (0, ""))
        r = self.run_kb("--no-global", "invoice extraction gemini")
        self.assertEqual((r.returncode, r.stdout), (0, ""))

    def test_stale_index_is_used_and_background_rebuild_started(self):
        self.run_kb("invoice extraction gemini")  # builds the index
        old = time.time() - 7 * 3600
        os.utime(self.index, (old, old))
        import json
        with open(self.index) as f:
            data = json.load(f)
        data["built"] = old
        with open(self.index, "w") as f:
            json.dump(data, f)
        os.utime(self.index, (old, old))
        # the stale index still answers although the page is gone from disk's keyword side
        marker = os.path.join(self.base, "rebuild-marker")
        fake = os.path.join(self.base, "fake-rebuild.sh")
        write(fake, "#!/bin/sh\necho started > '%s'\n" % marker)
        os.chmod(fake, 0o755)
        r = self.run_kb("invoice extraction gemini", env_extra={"KB_GLOBAL_REBUILD_CMD": fake})
        self.assertIn("[[abd/invoice-extraction]]", r.stdout)
        for _ in range(50):
            if os.path.exists(marker):
                break
            time.sleep(0.1)
        self.assertTrue(os.path.exists(marker))

    def test_fresh_index_does_not_rebuild(self):
        self.run_kb("invoice extraction gemini")
        marker = os.path.join(self.base, "rebuild-marker")
        fake = os.path.join(self.base, "fake-rebuild.sh")
        write(fake, "#!/bin/sh\necho started > '%s'\n" % marker)
        os.chmod(fake, 0o755)
        self.run_kb("invoice extraction gemini", env_extra={"KB_GLOBAL_REBUILD_CMD": fake})
        time.sleep(0.3)
        self.assertFalse(os.path.exists(marker))

    def test_rebuild_index_flag_writes_index_once_under_lock(self):
        self.run_kb("--rebuild-index")
        self.assertTrue(os.path.exists(self.index))
        lock = os.path.join(self.home, ".cache", "kb-retrieve", "rebuild.lock")
        self.assertFalse(os.path.exists(lock))
        os.unlink(self.index)
        write(lock, "")
        self.run_kb("--rebuild-index")
        self.assertFalse(os.path.exists(self.index))  # another rebuild holds the lock

    def test_global_hits_are_jev_screened(self):
        bindir = os.path.join(self.base, "bin")
        write(os.path.join(bindir, "jev"), FAKE_JEV)
        os.chmod(os.path.join(bindir, "jev"), 0o755)
        seen = os.path.join(self.base, "jev-seen.jsonl")
        env = {"PATH": bindir + os.pathsep + os.environ["PATH"], "KB_JEV": "1", "FAKE_JEV_SEEN": seen}
        r = self.run_kb("invoice extraction gemini", env_extra=env)
        self.assertIn("[[abd/invoice-extraction]]", r.stdout)
        self.assertTrue(os.path.exists(seen))


if __name__ == "__main__":
    unittest.main()
