"""Tests for scripts/park-skills.sh and install.sh's parked-skill/agent guards, on temp HOME dirs."""
import os
import re
import subprocess
import tempfile
import unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
PARK = os.path.join(ROOT, "scripts", "park-skills.sh")
INSTALL = os.path.join(ROOT, "install.sh")


def sh(cmd, home, *args):
    return subprocess.run(["bash", cmd, *args], env={**os.environ, "HOME": home, "CLAUDE_HOME": home + "/.claude"},
                          capture_output=True, text=True)


def skill(root, name, link_from=None):
    """Create <root>/<name>/SKILL.md (real dir), or a symlink to link_from."""
    os.makedirs(root, exist_ok=True)
    if link_from:
        os.symlink(link_from, os.path.join(root, name))
        return
    os.makedirs(os.path.join(root, name))
    with open(os.path.join(root, name, "SKILL.md"), "w") as f:
        f.write(f"---\nname: {name}\ndescription: d\n---\n")


class DedupeTest(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.home = self.t.name
        self.live = self.home + "/.claude/skills"
        self.parked = self.home + "/.claude/skills-parked"
        self.src = self.home + "/src"

    def tearDown(self):
        self.t.cleanup()

    def test_dedupe_removes_only_live_symlinks_with_valid_parked_copy(self):
        skill(self.src, "a")
        skill(self.src, "b")
        skill(self.parked, "a", self.src + "/a")      # dup, live is a symlink -> removed
        skill(self.live, "a", self.src + "/a")
        skill(self.parked, "real")                    # dup, but live is a real dir -> kept
        skill(self.live, "real")
        os.makedirs(self.parked + "/nomd")            # parked has no SKILL.md -> live kept
        skill(self.live, "nomd", self.src + "/b")
        skill(self.live, "only-live", self.src + "/b")
        r = sh(PARK, self.home, "dedupe")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(os.path.lexists(self.live + "/a"))
        self.assertTrue(os.path.isdir(self.live + "/real") and not os.path.islink(self.live + "/real"))
        self.assertTrue(os.path.islink(self.live + "/nomd"))
        self.assertTrue(os.path.islink(self.live + "/only-live"))
        self.assertIn("removed a", r.stdout)
        self.assertTrue(os.path.exists(self.src + "/a/SKILL.md"))

    def test_dedupe_keeps_live_symlink_when_parked_copy_is_a_different_target(self):
        skill(self.src, "a")
        skill(self.src + "-old", "a")                  # an older copy of the same skill
        skill(self.parked, "a", self.src + "-old/a")
        skill(self.live, "a", self.src + "/a")
        r = sh(PARK, self.home, "dedupe")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(os.readlink(self.live + "/a"), self.src + "/a")
        self.assertIn("differs", r.stdout)
        self.assertNotIn("removed a", r.stdout)

    def test_dedupe_removes_when_both_resolve_to_the_same_real_path(self):
        skill(self.src, "a")
        os.symlink(self.src, self.home + "/src-alias")   # parked goes through a second symlink
        skill(self.parked, "a", self.home + "/src-alias/a")
        skill(self.live, "a", self.src + "/a")
        r = sh(PARK, self.home, "dedupe")
        self.assertIn("removed a", r.stdout)
        self.assertFalse(os.path.lexists(self.live + "/a"))

    def test_dedupe_dry_run_changes_nothing(self):
        skill(self.src, "a")
        skill(self.parked, "a", self.src + "/a")
        skill(self.live, "a", self.src + "/a")
        r = sh(PARK, self.home, "dedupe", "--dry-run")
        self.assertIn("would remove a", r.stdout)
        self.assertTrue(os.path.islink(self.live + "/a"))


class AgentParkTest(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.home = self.t.name
        self.live = self.home + "/.claude/agents"
        self.parked = self.home + "/.claude/agents-parked"
        os.makedirs(self.live)
        for n in ("a", "b", "c"):
            with open(f"{self.live}/{n}.md", "w") as f:
                f.write(n)
        os.symlink(self.live + "/a.md", self.live + "/link.md")

    def tearDown(self):
        self.t.cleanup()

    def test_park_and_unpark_agent(self):
        r = sh(PARK, self.home, "park-agent", "a", "b")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(os.path.exists(self.parked + "/b.md") and os.path.lexists(self.parked + "/a.md"))
        self.assertFalse(os.path.lexists(self.live + "/a.md"))
        sh(PARK, self.home, "unpark-agent", "a")
        self.assertTrue(os.path.lexists(self.live + "/a.md"))
        self.assertFalse(os.path.lexists(self.parked + "/a.md"))
        sh(PARK, self.home, "unpark-agent", "--all")
        self.assertTrue(os.path.exists(self.live + "/b.md"))
        self.assertEqual(os.listdir(self.parked), [])

    def test_symlink_stays_symlink(self):
        sh(PARK, self.home, "park-agent", "link")
        self.assertTrue(os.path.islink(self.parked + "/link.md"))

    def test_keep_agents_parks_the_rest(self):
        sh(PARK, self.home, "keep-agents", "a", "link")
        self.assertEqual(sorted(os.listdir(self.live)), ["a.md", "link.md"])
        self.assertEqual(sorted(os.listdir(self.parked)), ["b.md", "c.md"])

    def test_dry_run(self):
        r = sh(PARK, self.home, "park-agent", "a", "--dry-run")
        self.assertIn("would move a", r.stdout)
        self.assertTrue(os.path.exists(self.live + "/a.md"))


class InstallGuardTest(unittest.TestCase):
    """install.sh must not re-link anything that is parked."""

    def run_install_fn(self, home, body):
        # Extract only the function definitions and the variables they need.
        src = open(INSTALL).read()
        fns = [re.search(rf"^\s*{n}\(\) \{{.*?\n\s*\}}\n", src, re.S | re.M).group(0)
               for n in ("link_skill", "link_agent")]
        script = (f'set -euo pipefail\nupdate_symlinks=0\nCLAUDE_HOME="{home}/.claude"\n'
                  'SKILLS_DIR="$CLAUDE_HOME/skills"\nAGENTS_DIR="$CLAUDE_HOME/agents"\n'
                  'mkdir -p "$SKILLS_DIR" "$AGENTS_DIR"\n' + "".join(fns) + body)
        return subprocess.run(["bash", "-c", script], capture_output=True, text=True)

    def test_link_skill_skips_parked(self):
        with tempfile.TemporaryDirectory() as home:
            skill(home + "/.claude/skills-parked", "video-use")
            os.makedirs(home + "/repo/video-use")
            os.makedirs(home + "/repo/other")
            r = self.run_install_fn(home, f'link_skill "{home}/repo/video-use"\nlink_skill "{home}/repo/other"\n')
            self.assertIn("parked   video-use", r.stdout, r.stderr)
            self.assertFalse(os.path.lexists(home + "/.claude/skills/video-use"))
            self.assertTrue(os.path.islink(home + "/.claude/skills/other"))

    def test_link_agent_skips_parked(self):
        with tempfile.TemporaryDirectory() as home:
            os.makedirs(home + "/.claude/agents-parked")
            open(home + "/.claude/agents-parked/debugger.md", "w").write("x")
            os.makedirs(home + "/repo")
            for n in ("debugger", "planner"):
                open(f"{home}/repo/{n}.md", "w").write("x")
            r = self.run_install_fn(home, f'link_agent "{home}/repo/debugger.md"\nlink_agent "{home}/repo/planner.md"\n')
            self.assertIn("parked   debugger.md", r.stdout, r.stderr)
            self.assertFalse(os.path.lexists(home + "/.claude/agents/debugger.md"))
            self.assertTrue(os.path.islink(home + "/.claude/agents/planner.md"))


if __name__ == "__main__":
    unittest.main()
