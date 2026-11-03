#!/usr/bin/env python3
"""Tests for the grok AGENTS.md shrink in scripts/sync-rules-harnesses.py.

Run: python3 scripts/tests/test_sync_rules_harnesses.py
"""
import importlib.util
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
MOD_PATH = os.path.join(HERE, "..", "sync-rules-harnesses.py")
spec = importlib.util.spec_from_file_location("sync_rules_harnesses", MOD_PATH)
srh = importlib.util.module_from_spec(spec)
spec.loader.exec_module(srh)

BEGIN, END = srh.BEGIN, srh.END


def make_block():
    return (
        f"{BEGIN} (test) -->\n# Global standing rules\n\n"
        "## COMMUNICATION CONTRACT — read `~/.claude/comms.md`\n" + "c" * 120 + "\n\n"
        "## TOKEN BUDGET: loops live in code\n" + "t" * 900 + "\n\n"
        "## SERVER-FIRST: website work\n" + "s" * 150 + "\n\n"
        "## BRANCH LOCKS: one agent per branch\n" + "b" * 150 + "\n\n"
        "## KB + SPEC CHAIN (detail: `~/.claude/reference/kb-chain.md`)\n" + "k" * 500 + "\n\n"
        "### Project-level overrides\n" + "p" * 300 + "\n\n"
        "### Deployment\n" + "d" * 200 + "\n"
        f"{END}"
    )


class ShrinkPreferenceList(unittest.TestCase):
    def test_under_cap_is_untouched(self):
        block = make_block()
        self.assertEqual(srh.shrink_to_cap(block, len(block)), block)

    def test_kb_chain_shrinks_first_and_alone_when_enough(self):
        block = make_block()
        out = srh.shrink_to_cap(block, len(block) - 100)
        self.assertIn("full text: ~/.claude/CLAUDE.md, section KB + SPEC CHAIN", out)
        self.assertNotIn("k" * 10, out)
        self.assertIn("p" * 300, out)
        self.assertIn("d" * 200, out)

    def test_project_then_deployment_only_when_still_over(self):
        block = make_block()
        out = srh.shrink_to_cap(block, 300)
        self.assertIn("section KB + SPEC CHAIN", out)
        self.assertIn("section Project-level overrides", out)
        self.assertIn("section Deployment", out)
        self.assertNotIn("p" * 10, out)
        self.assertNotIn("d" * 10, out)

    def test_never_shrink_sections_survive(self):
        block = make_block()
        out = srh.shrink_to_cap(block, 1)
        self.assertIn("t" * 900, out)
        self.assertIn("c" * 120, out)
        self.assertIn("s" * 150, out)
        self.assertIn("b" * 150, out)
        self.assertTrue(out.endswith(END))

    def test_impossible_cap_returns_still_over_block(self):
        block = make_block()
        out = srh.shrink_to_cap(block, 1)
        self.assertGreater(len(out), 1)
        self.assertIn("TOKEN BUDGET", out)

    def test_shrink_is_idempotent(self):
        block = make_block()
        once = srh.shrink_to_cap(block, len(block) - 100)
        self.assertEqual(srh.shrink_to_cap(once, len(once)), once)
        self.assertEqual(once.count("full text: ~/.claude/CLAUDE.md, section KB + SPEC CHAIN"), 1)


if __name__ == "__main__":
    unittest.main()
