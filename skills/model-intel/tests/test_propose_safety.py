"""propose_tiers safety: structured pins, one fresh backup per apply, --dry-run never probes."""
import json
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_model_intel as base  # noqa: E402
from test_model_intel import SKILL, propose_tiers, row  # noqa: E402


class ProposeCase(base.Base):
    def setUp(self):
        super().setUp()
        self.t = self.base_tiers()
        self.inc = row("mimoold", "Mimo Old", "medium", 40.0, 0.50, 100, "Xiaomi")
        chain = ["cliproxy/claude-sonnet-5-5", "opencode-go/mimo-old"]
        self.t["tiers"] = {"T3": list(chain)}
        self.t["kinds"] = {"general": {"T3": list(chain)}, "language": {"T3": ["commandcode/gpt-6-luna"]}}

    def go(self, cand, probe=lambda m: True):
        rows = [self.inc, cand]
        return propose_tiers.decide(self.t, rows, {"models": {r["key"]: r["reach"] for r in rows}}, probe)


class StructuredPins(ProposeCase):
    def test_pins_come_from_structured_keys_never_from_comment_text(self):
        real = json.loads((SKILL / "config" / "owner_rules.json").read_text())["pinned_entries"]["chains"]
        for chain in ("kinds.language", "kinds.review", "kinds.test", "kinds.judge"):
            self.assertIn(chain, real)
        for comment in ([], ["2026-10-22 note reworded, nothing about languages"]):
            self.t["_comment"] = comment
            self.t.pop("_pinned", None)
            self.assertTrue(set(real) <= propose_tiers.pinned(self.t), comment)
        self.t["_comment"] = ["owner: kinds.code is pinned"]   # free text does not pin
        self.assertNotIn("kinds.code", propose_tiers.pinned(self.t))
        self.t["_pinned"] = ["kinds.code"]                     # the structured key does
        self.assertIn("kinds.code", propose_tiers.pinned(self.t))

    def test_language_chain_stays_pinned_without_any_comment(self):
        self.t["_comment"] = []
        auto, _ = self.go(row("newgpt", "New GPT", "medium", 60.0, 0.01, 90, creator="OpenAI"))
        self.assertFalse(any(a["chain"].startswith("kinds.language") for a in auto))


class Backups(ProposeCase):
    def test_every_apply_writes_its_own_backup_and_restores_its_own_start(self):
        self.t["kinds"] = {}
        self.tiers.write_text(json.dumps(self.t, indent=2))
        auto, _ = self.go(row("newmodel", "New Model", "medium", 45.0, 0.40, 90))
        b1 = propose_tiers.apply_changes(self.tiers, auto, "2026-10-11")
        after_first = self.tiers.read_text()
        # second run the same day, different candidate, validation fails
        os.environ["MODEL_INTEL_VALIDATE_CMD"] = "false"
        self.addCleanup(os.environ.__setitem__, "MODEL_INTEL_VALIDATE_CMD", "true")
        self.t = json.loads(after_first)
        auto2, _ = self.go(row("other", "Other Model", "medium", 46.0, 0.30, 90))
        self.assertTrue(auto2)
        with self.assertRaises(RuntimeError):
            propose_tiers.apply_changes(self.tiers, auto2, "2026-10-11")
        self.assertEqual(self.tiers.read_text(), after_first)          # the first apply survives
        self.assertEqual(b1.name, "tiers.json.bak-model-intel-2026-10-11")
        self.assertTrue((self.tmp / "tiers.json.bak-model-intel-2026-10-11.2").exists())
        self.assertNotIn("opencode-go/newmodel", b1.read_text())        # original backup untouched


if __name__ == "__main__":
    unittest.main()
