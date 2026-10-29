import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "refresh-rule.sh"
BEGIN = "<!-- BEGIN AUTO-GENERATED: dev-stack-state do-not-edit-by-hand -->"
END = "<!-- END AUTO-GENERATED: dev-stack-state -->"


class RefreshRuleAgentCountTests(unittest.TestCase):
    def run_refresh(self, setup):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            claude = home / ".claude"
            claude.mkdir()
            (claude / "skills").mkdir()
            (claude / "CLAUDE.md").write_text(f"{BEGIN}\nold\n{END}\n")
            dev_stack = home / "repo"
            (dev_stack / "bin").mkdir(parents=True)
            setup(claude)
            env = os.environ.copy()
            env.update(HOME=str(home), DEV_STACK=str(dev_stack), CLAUDE_MD=str(claude / "CLAUDE.md"))
            return subprocess.run(["bash", str(SCRIPT), "--dry-run"], cwd=ROOT, env=env,
                                  text=True, capture_output=True)

    def test_missing_agents_directory_has_no_integer_expression_error(self):
        result = self.run_refresh(lambda claude: None)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("integer expression expected", result.stderr)
        self.assertNotIn("Registered subagents", result.stdout)

    def test_empty_agents_directory_has_no_integer_expression_error(self):
        def setup(claude):
            (claude / "agents").mkdir()
        result = self.run_refresh(setup)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("integer expression expected", result.stderr)
        self.assertNotIn("Registered subagents", result.stdout)

    def test_parked_agents_are_reported_when_none_are_loaded(self):
        def setup(claude):
            parked = claude / "agents-parked"
            parked.mkdir()
            (parked / "debugger.md").write_text("---\nmodel: opus\n---\n")
            (parked / "planner.md").write_text("---\nmodel: sonnet\n---\n")
        result = self.run_refresh(setup)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("**Subagents:** none loaded; 2 parked in ~/.claude/agents-parked (use jdelegate --role <name>).", result.stdout)
        self.assertNotIn("Registered subagents", result.stdout)

    def test_symlinked_parked_agent_is_reported(self):
        def setup(claude):
            parked = claude / "agents-parked"
            parked.mkdir()
            target = claude / "parked-reviewer.md"
            target.write_text("---\nmodel: opus\n---\n")
            (parked / "reviewer.md").symlink_to(target)
        result = self.run_refresh(setup)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("**Subagents:** none loaded; 1 parked in ~/.claude/agents-parked (use jdelegate --role <name>).", result.stdout)

    def test_loaded_agents_keep_the_registered_table(self):
        def setup(claude):
            agents = claude / "agents"
            agents.mkdir()
            (agents / "reviewer.md").write_text("---\nmodel: opus\n---\n")
        result = self.run_refresh(setup)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("**Registered subagents (1 total):**", result.stdout)
        self.assertIn("| `reviewer` | external | opus |", result.stdout)


if __name__ == "__main__":
    unittest.main()
