"""Tests for bin/lock-checks (real temp git repos, no network)."""
import json
import os
import subprocess
import tempfile
import unittest

BIN = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "bin", "lock-checks"))


def sh(cwd, *args, env=None):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, env={**os.environ, "GIT_CONFIG_GLOBAL": "/dev/null", **(env or {})})


class LockChecksTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = os.path.realpath(self.tmp.name)
        sh(self.repo, "git", "init", "-q", "-b", "feat")
        # a developer's global core.hooksPath must not capture (or be modified by) these tests
        sh(self.repo, "git", "config", "core.hooksPath", ".git/hooks")
        sh(self.repo, "git", "config", "user.email", "t@example.com")
        sh(self.repo, "git", "config", "user.name", "t")
        sh(self.repo, "git", "config", "commit.gpgsign", "false")
        os.makedirs(os.path.join(self.repo, "tests"))
        self.write("tests/test_a.py", "def test_one():\n    assert 1\n\ndef test_two():\n    assert 2\n")
        self.write("README.md", "x\n")
        sh(self.repo, "git", "add", "-A")
        sh(self.repo, "git", "commit", "-q", "-m", "init")

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, rel, text):
        p = os.path.join(self.repo, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w") as f:
            f.write(text)

    def exists(self, rel):
        return os.path.exists(os.path.join(self.repo, rel))

    def lc(self, *args, **kw):
        return sh(self.repo, BIN, *args, **kw)

    def settings(self):
        with open(os.path.join(self.repo, ".claude", "settings.json")) as f:
            return json.load(f)

    def test_list_prints_one_line_per_check(self):
        r = self.lc("list", "tests/test_a.py")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("test_one", r.stdout)
        self.assertIn("test_two", r.stdout)
        self.assertEqual(len(r.stdout.strip().splitlines()), 2)

    def test_approve_moves_writes_deny_and_commits(self):
        r = self.lc("approve", "tests/test_a.py")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(self.exists("tests/test_a.py"))
        self.assertTrue(self.exists("tests/locked/test_a.py"))
        deny = self.settings()["permissions"]["deny"]
        self.assertIn("Edit(tests/locked/**)", deny)
        self.assertNotIn("Write(tests/locked/**)", deny)
        log = sh(self.repo, "git", "log", "-1", "--format=%B").stdout
        self.assertEqual(log.strip(), "test: lock approved checks")
        self.assertEqual(sh(self.repo, "git", "status", "--porcelain").stdout.strip(), "")

    def test_approve_idempotent_and_keeps_existing_settings(self):
        self.write(".claude/settings.json", json.dumps(
            {"model": "x", "permissions": {"allow": ["Bash(ls)"], "deny": ["Read(.env)"]}}))
        self.write("tests/test_b.py", "def test_b():\n    pass\n")
        sh(self.repo, "git", "add", "-A")
        sh(self.repo, "git", "commit", "-q", "-m", "more")
        self.assertEqual(self.lc("approve", "tests/test_a.py").returncode, 0)
        self.assertEqual(self.lc("approve", "tests/test_b.py").returncode, 0)
        s = self.settings()
        self.assertEqual(s["model"], "x")
        self.assertEqual(s["permissions"]["allow"], ["Bash(ls)"])
        deny = s["permissions"]["deny"]
        self.assertEqual(deny.count("Edit(tests/locked/**)"), 1)
        self.assertEqual(deny.count("Write(tests/locked/**)"), 0)
        self.assertIn("Read(.env)", deny)

    def test_approve_migrates_old_write_rule_and_keeps_others(self):
        self.write(".claude/settings.json", json.dumps({"permissions": {"deny": [
            "Read(.env)", "Write(tests/locked/**)", "Write(other/**)"]}}))
        sh(self.repo, "git", "add", "-A")
        sh(self.repo, "git", "commit", "-q", "-m", "settings")
        self.assertEqual(self.lc("approve", "tests/test_a.py").returncode, 0)
        deny = self.settings()["permissions"]["deny"]
        self.assertEqual(deny, ["Read(.env)", "Write(other/**)", "Edit(tests/locked/**)"])

    def test_verify_clean_then_fails_after_edit(self):
        self.lc("approve", "tests/test_a.py")
        self.assertEqual(self.lc("verify").returncode, 0)
        self.write("tests/locked/test_a.py", "def test_one():\n    pass\n")
        r = self.lc("verify")
        self.assertEqual(r.returncode, 1)
        self.assertIn("tests/locked/test_a.py", r.stdout + r.stderr)

    def test_verify_fails_on_untracked_file(self):
        self.lc("approve", "tests/test_a.py")
        self.write("tests/locked/test_new.py", "def test_new():\n    pass\n")
        r = self.lc("verify")
        self.assertEqual(r.returncode, 1)
        self.assertIn("tests/locked/test_new.py", r.stdout + r.stderr)

    def test_approve_refuses_missing_path(self):
        r = self.lc("approve", "tests/nope.py")
        self.assertNotEqual(r.returncode, 0)
        self.assertTrue(self.exists("tests/test_a.py"))
        self.assertFalse(self.exists(".claude/settings.json"))

    def test_approve_refuses_outside_git_repo(self):
        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d, "t.py"), "w").close()
            r = sh(os.path.realpath(d), BIN, "approve", "t.py", env={"GIT_CEILING_DIRECTORIES": os.path.dirname(os.path.realpath(d))})
            self.assertNotEqual(r.returncode, 0)

    def test_unlock_moves_back_and_drops_deny_when_empty(self):
        self.lc("approve", "tests/test_a.py")
        r = self.lc("unlock", "tests/locked/test_a.py")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("human", (r.stdout + r.stderr).lower())
        self.assertTrue(self.exists("tests/test_a.py"))
        self.assertFalse(self.exists("tests/locked/test_a.py"))
        self.assertNotIn("Edit(tests/locked/**)", self.settings()["permissions"]["deny"])

    def test_custom_locked_dir(self):
        r = self.lc("approve", "tests/test_a.py", env={"LOCKED_DIR": "checks/locked"})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(self.exists("checks/locked/test_a.py"))
        self.assertIn("Edit(checks/locked/**)", self.settings()["permissions"]["deny"])

    # ---- pre-commit hook ----
    def hook_path(self):
        return os.path.join(self.repo, ".git", "hooks", "pre-commit")

    def stage_locked_edit(self):
        self.lc("approve", "tests/test_a.py")
        self.write("tests/locked/test_a.py", "def test_one():\n    assert 0\n")
        sh(self.repo, "git", "add", "-A")

    def test_install_hook_is_idempotent(self):
        for _ in range(2):
            r = self.lc("install-hook")
            self.assertEqual(r.returncode, 0, r.stderr)
        with open(self.hook_path()) as f:
            text = f.read()
        self.assertEqual(text.count("# lock-checks pre-commit hook"), 1)
        self.assertTrue(os.access(self.hook_path(), os.X_OK))

    def test_hook_blocks_staged_edit_under_locked_dir(self):
        self.stage_locked_edit()
        r = sh(self.repo, "git", "commit", "-q", "-m", "tamper")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("tests/locked/test_a.py", r.stdout + r.stderr)

    def test_hook_allows_with_unlock_env(self):
        self.stage_locked_edit()
        r = sh(self.repo, "git", "commit", "-q", "-m", "human edit", env={"LOCK_CHECKS_UNLOCK": "1"})
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_hook_ignores_commits_outside_locked_dir(self):
        self.lc("approve", "tests/test_a.py")
        self.write("README.md", "y\n")
        sh(self.repo, "git", "add", "-A")
        r = sh(self.repo, "git", "commit", "-q", "-m", "docs")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_approve_installs_hook_and_still_commits(self):
        r = self.lc("approve", "tests/test_a.py")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("# lock-checks pre-commit hook", open(self.hook_path()).read())
        log = sh(self.repo, "git", "log", "-1", "--format=%s").stdout.strip()
        self.assertEqual(log, "test: lock approved checks")

    def test_approve_a_second_file_commits_through_the_hook(self):
        self.write("tests/test_b.py", "def test_b():\n    assert 1\n")
        sh(self.repo, "git", "add", "-A")
        sh(self.repo, "git", "commit", "-q", "-m", "b")
        self.assertEqual(self.lc("approve", "tests/test_a.py").returncode, 0)
        r = self.lc("approve", "tests/test_b.py")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(self.exists("tests/locked/test_b.py"))

    def test_install_hook_preserves_existing_pre_commit(self):
        os.makedirs(os.path.dirname(self.hook_path()), exist_ok=True)
        with open(self.hook_path(), "w") as f:
            f.write("#!/bin/sh\necho EXISTING-HOOK-RAN\n")
        os.chmod(self.hook_path(), 0o755)
        self.assertEqual(self.lc("install-hook").returncode, 0)
        self.assertEqual(self.lc("install-hook").returncode, 0)
        text = open(self.hook_path()).read()
        self.assertIn("EXISTING-HOOK-RAN", text)
        self.assertEqual(text.count("# lock-checks pre-commit hook"), 1)
        self.assertTrue(text.startswith("#!/bin/sh\n"))
        self.write("README.md", "z\n")
        sh(self.repo, "git", "add", "-A")
        r = sh(self.repo, "git", "commit", "-m", "x")
        self.assertIn("EXISTING-HOOK-RAN", r.stdout + r.stderr)

    def test_hook_honours_custom_locked_dir(self):
        env = {"LOCKED_DIR": "checks/locked"}
        self.lc("approve", "tests/test_a.py", env=env)
        self.write("checks/locked/test_a.py", "tampered\n")
        sh(self.repo, "git", "add", "-A")
        r = sh(self.repo, "git", "commit", "-q", "-m", "t", env=env)
        self.assertNotEqual(r.returncode, 0)

    def test_unlock_prints_env_var_for_follow_up_commit(self):
        self.lc("approve", "tests/test_a.py")
        r = self.lc("unlock", "tests/locked/test_a.py")
        self.assertIn("LOCK_CHECKS_UNLOCK=1", r.stdout)

    # ---- review fixes ----
    def commit_all(self, msg, env=None, *flags):
        sh(self.repo, "git", "add", "-A")
        return sh(self.repo, "git", "commit", "-q", *flags, "-m", msg, env=env)

    def test_hook_message_does_not_print_the_bypass(self):
        self.stage_locked_edit()
        r = sh(self.repo, "git", "commit", "-q", "-m", "tamper")
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("LOCK_CHECKS_UNLOCK", r.stdout + r.stderr)

    def test_help_documents_the_env_bypass(self):
        self.assertIn("LOCK_CHECKS_UNLOCK", self.lc("-h").stdout)

    def test_verify_fails_after_committed_tamper_with_env(self):
        self.lc("approve", "tests/test_a.py")
        self.write("tests/locked/test_a.py", "def test_one():\n    pass\n")
        r = self.commit_all("tamper", {"LOCK_CHECKS_UNLOCK": "1"})
        self.assertEqual(r.returncode, 0, r.stderr)
        v = self.lc("verify")
        self.assertEqual(v.returncode, 1)
        self.assertIn("tests/locked/test_a.py", v.stdout)

    def test_verify_fails_after_no_verify_commit(self):
        self.lc("approve", "tests/test_a.py")
        self.write("tests/locked/test_a.py", "def test_one():\n    pass\n")
        r = self.commit_all("tamper", None, "--no-verify")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.lc("verify").returncode, 1)

    def test_verify_fails_after_committed_new_and_deleted_files(self):
        self.lc("approve", "tests/test_a.py")
        os.remove(os.path.join(self.repo, "tests/locked/test_a.py"))
        self.write("tests/locked/test_n.py", "x\n")
        self.commit_all("t", None, "--no-verify")
        v = self.lc("verify")
        self.assertEqual(v.returncode, 1)
        self.assertIn("tests/locked/test_a.py", v.stdout)
        self.assertIn("tests/locked/test_n.py", v.stdout)

    def test_verify_ok_after_unlock_and_after_second_approve(self):
        self.write("tests/test_b.py", "def test_b():\n    pass\n")
        self.commit_all("b")
        self.lc("approve", "tests/test_a.py")
        self.lc("approve", "tests/test_b.py")
        self.assertEqual(self.lc("verify").returncode, 0)
        self.lc("unlock", "tests/locked/test_b.py")
        self.assertEqual(self.lc("verify").returncode, 0)

    def test_manifest_lives_outside_the_worktree(self):
        self.lc("approve", "tests/test_a.py")
        man = os.path.join(self.repo, ".git", "lock-checks", "manifest")
        self.assertIn("tests/locked", open(man).read())
        self.assertNotIn("lock-checks", sh(self.repo, "git", "ls-files").stdout)

    def test_hook_runs_in_linked_worktree(self):
        sh(self.repo, "git", "config", "--unset", "core.hooksPath")
        self.lc("approve", "tests/test_a.py")
        wt = os.path.join(self.repo, "wt")
        r = sh(self.repo, "git", "worktree", "add", "-q", "-b", "wtbranch", wt)
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(os.path.join(wt, "tests/locked/test_a.py"), "w") as f:
            f.write("tampered\n")
        sh(wt, "git", "add", "-A")
        r = sh(wt, "git", "commit", "-q", "-m", "tamper")
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("rejected", r.stdout + r.stderr)

    def test_unlock_refuses_to_overwrite_existing_test(self):
        self.lc("approve", "tests/test_a.py")
        self.write("tests/test_a.py", "mine\n")
        r = self.lc("unlock", "tests/locked/test_a.py")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("refusing", r.stderr)
        self.assertEqual(open(os.path.join(self.repo, "tests/test_a.py")).read(), "mine\n")
        self.assertTrue(self.exists("tests/locked/test_a.py"))

    def test_approve_works_when_claude_dir_is_gitignored(self):
        self.write(".gitignore", ".claude/\n")
        self.commit_all("ignore")
        r = self.lc("approve", "tests/test_a.py")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(".claude/settings.json", sh(self.repo, "git", "ls-files").stdout)
        self.assertEqual(sh(self.repo, "git", "status", "--porcelain").stdout.strip(), "")

    def failing_hook(self):
        os.makedirs(os.path.dirname(self.hook_path()), exist_ok=True)
        with open(self.hook_path(), "w") as f:
            f.write("#!/bin/sh\necho NOPE >&2\nexit 1\n")
        os.chmod(self.hook_path(), 0o755)

    def test_approve_rolls_back_when_commit_fails(self):
        self.failing_hook()
        before = sh(self.repo, "git", "status", "--porcelain").stdout
        r = self.lc("approve", "tests/test_a.py")
        self.assertNotEqual(r.returncode, 0)
        self.assertTrue(self.exists("tests/test_a.py"))
        self.assertFalse(self.exists("tests/locked"))
        self.assertFalse(self.exists(".claude"))
        self.assertEqual(sh(self.repo, "git", "status", "--porcelain").stdout, before)
        self.assertEqual(sh(self.repo, "git", "diff", "--cached", "--name-only").stdout, "")
        self.assertFalse(os.path.exists(os.path.join(self.repo, ".git", "lock-checks", "manifest")))

    def test_approve_rollback_restores_existing_settings(self):
        self.write(".claude/settings.json", '{"model": "x"}\n')
        self.commit_all("s")
        self.failing_hook()
        r = self.lc("approve", "tests/test_a.py")
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(open(os.path.join(self.repo, ".claude/settings.json")).read(), '{"model": "x"}\n')
        self.assertEqual(sh(self.repo, "git", "status", "--porcelain").stdout, "")

    def test_locked_dir_env_at_commit_time_cannot_bypass(self):
        self.stage_locked_edit()
        r = sh(self.repo, "git", "commit", "-q", "-m", "t", env={"LOCKED_DIR": "nope"})
        self.assertNotEqual(r.returncode, 0)

    def test_second_locked_dir_is_protected_too(self):
        self.write("tests/test_b.py", "def test_b():\n    pass\n")
        self.commit_all("b")
        self.lc("approve", "tests/test_a.py")
        self.lc("approve", "tests/test_b.py", env={"LOCKED_DIR": "checks/locked"})
        for f in ("tests/locked/test_a.py", "checks/locked/test_b.py"):
            self.write(f, "tampered\n")
            sh(self.repo, "git", "add", "-A")
            r = sh(self.repo, "git", "commit", "-q", "-m", "t")
            self.assertNotEqual(r.returncode, 0, f)
            sh(self.repo, "git", "reset", "-q", "--hard")

    # ---- legacy repos (locked dir committed by an older version, no manifest entry) ----
    def legacy_repo(self):
        self.write("tests/locked/test_a.py", "def test_one():\n    assert 1\n")
        self.commit_all("legacy lock")
        self.assertFalse(os.path.exists(os.path.join(self.repo, ".git", "lock-checks", "manifest")))

    def test_legacy_verify_clean_passes_with_warning(self):
        self.legacy_repo()
        r = self.lc("verify")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("lock-checks: no approval record for tests/locked; comparing against HEAD. Run `lock-checks rebaseline` to record it.", r.stderr)
        self.assertEqual(r.stderr.count("no approval record"), 1)

    def test_legacy_verify_fails_on_uncommitted_tamper_and_untracked(self):
        self.legacy_repo()
        self.write("tests/locked/test_a.py", "def test_one():\n    pass\n")
        r = self.lc("verify")
        self.assertEqual(r.returncode, 1)
        self.assertIn("tests/locked/test_a.py", r.stdout)
        sh(self.repo, "git", "checkout", "-q", "--", "tests/locked")
        self.write("tests/locked/test_new.py", "x\n")
        r = self.lc("verify")
        self.assertEqual(r.returncode, 1)
        self.assertIn("tests/locked/test_new.py", r.stdout)

    def test_rebaseline_records_then_committed_tamper_fails_strict(self):
        self.legacy_repo()
        r = self.lc("rebaseline")
        self.assertEqual(r.returncode, 0, r.stderr)
        v = self.lc("verify")
        self.assertEqual(v.returncode, 0, v.stdout + v.stderr)
        self.assertNotIn("no approval record", v.stderr)
        self.write("tests/locked/test_a.py", "def test_one():\n    pass\n")
        self.commit_all("tamper", None, "--no-verify")
        v = self.lc("verify")
        self.assertEqual(v.returncode, 1)
        self.assertIn("tests/locked/test_a.py", v.stdout)

    def test_rebaseline_refuses_dirty_dir(self):
        self.legacy_repo()
        self.write("tests/locked/test_a.py", "def test_one():\n    pass\n")
        r = self.lc("rebaseline")
        self.assertNotEqual(r.returncode, 0)
        self.assertFalse(os.path.exists(os.path.join(self.repo, ".git", "lock-checks", "manifest")))

    def test_help_documents_rebaseline_as_human_action(self):
        out = self.lc("-h").stdout
        self.assertIn("rebaseline", out)
        self.assertIn("HUMAN ONLY", out.split("rebaseline", 1)[1].split("\n  unlock")[0])

    def test_husky_layout_appends_to_husky_pre_commit(self):
        os.makedirs(os.path.join(self.repo, ".husky", "_"))
        self.write(".husky/pre-commit", "echo HUSKY-RAN\n")
        self.write(".husky/_/pre-commit", "#!/bin/sh\nsh .husky/pre-commit\n")
        os.chmod(os.path.join(self.repo, ".husky/_/pre-commit"), 0o755)
        sh(self.repo, "git", "config", "core.hooksPath", ".husky/_")
        self.commit_all("husky")
        r = self.lc("approve", "tests/test_a.py")
        self.assertEqual(r.returncode, 0, r.stderr)
        text = open(os.path.join(self.repo, ".husky/pre-commit")).read()
        self.assertIn("# lock-checks pre-commit hook", text)
        self.assertIn("HUSKY-RAN", text)
        self.write("tests/locked/test_a.py", "t\n")
        sh(self.repo, "git", "add", "-A")
        r = sh(self.repo, "git", "commit", "-q", "-m", "t")
        self.assertNotEqual(r.returncode, 0)


if __name__ == "__main__":
    unittest.main()
