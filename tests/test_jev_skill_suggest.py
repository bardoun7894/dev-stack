"""Tests for bin/jev-skill-suggest policy (Jev stubbed, no network)."""
import os
import tempfile
import unittest

from test_jev_log import load

sug = load("jev-skill-suggest")


class FrontmatterTest(unittest.TestCase):
    def test_plain(self):
        fm = sug.frontmatter("---\nname: jev\ndescription: Typed decisions. Use for triage.\n---\n# Jev\nbody")
        self.assertEqual(fm, {"name": "jev", "description": "Typed decisions. Use for triage."})

    def test_folded_and_quoted(self):
        text = "---\nname: \"typesafe-ai\"\nlicense: MIT\ndescription: >\n  Build with TypeSafe.\n  Use when routing.\n---\nbody"
        fm = sug.frontmatter(text)
        self.assertEqual(fm["name"], "typesafe-ai")
        self.assertEqual(fm["description"], "Build with TypeSafe. Use when routing.")

    def test_no_frontmatter(self):
        self.assertEqual(sug.frontmatter("# just a readme"), {})


class RosterTest(unittest.TestCase):
    def test_reads_skill_dirs_and_body_excerpt(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "a"))
            with open(os.path.join(d, "a", "SKILL.md"), "w") as f:
                f.write("---\nname: alpha\ndescription: Does A.\n---\n# Alpha\nStep one.")
            os.makedirs(os.path.join(d, "broken"))
            with open(os.path.join(d, "broken", "SKILL.md"), "w") as f:
                f.write("no frontmatter")
            roster = sug.build_roster([(d, "")])
        self.assertEqual(list(roster), ["alpha"])
        self.assertEqual(roster["alpha"]["description"], "Does A.")
        self.assertIn("Step one.", roster["alpha"]["excerpt"])


class ParkedTest(unittest.TestCase):
    """Parked skills are not loaded into the session; Jev still ranks them and the hint points at SKILL.md."""

    def test_roster_marks_parked_skills_with_their_path(self):
        with tempfile.TemporaryDirectory() as d:
            live, parked = os.path.join(d, "skills"), os.path.join(d, "skills-parked")
            for root, name in ((live, "tdd"), (parked, "video-use")):
                os.makedirs(os.path.join(root, name))
                with open(os.path.join(root, name, "SKILL.md"), "w") as f:
                    f.write(f"---\nname: {name}\ndescription: Does {name}.\n---\nbody")
            roster = sug._roster_from(sug.skill_files(live_dir=live, parked_dir=parked, plugins=False))
        self.assertNotIn("parked", roster["tdd"])
        self.assertEqual(roster["video-use"]["parked"], os.path.join(parked, "video-use", "SKILL.md"))

    def test_hint_for_parked_skill_says_to_read_the_file(self):
        roster = {"tdd": {"description": "x", "excerpt": ""},
                  "video-use": {"description": "y", "excerpt": "", "parked": "/p/video-use/SKILL.md"}}
        self.assertIn("Relevant to the current request: tdd.", sug.hint("tdd", roster))
        h = sug.hint("video-use", roster)
        self.assertIn("/p/video-use/SKILL.md", h)
        self.assertIn("parked", h)


class PolicyTest(unittest.TestCase):
    def test_gate_mean_inverts_prose_suffices(self):
        answers = {"acts_on_user_system": {"noul": 0.9}, "would_follow_documented_procedure": {"noul": 0.6},
                   "prose_suffices": {"noul": 0.0}}
        self.assertAlmostEqual(sug.gate_score(answers), (0.9 + 0.6 + 1.0) / 3)

    def test_ranked_orders_by_probability(self):
        wide = {"type": "choice", "choice": "b", "probabilities": {"a": 0.1, "b": 0.7, "c": 0.2}}
        self.assertEqual(sug.ranked(wide, 2), ["b", "c"])

    def test_suggest_nothing_when_gate_low(self):
        calls = []

        def fake(state, questions, tag=None, timeout=None):
            calls.append(questions)
            return ({"skill": {"type": "choice", "choice": "a", "probabilities": {"a": 1}},
                     "acts_on_user_system": {"noul": 0.1}, "would_follow_documented_procedure": {"noul": 0.1},
                     "prose_suffices": {"noul": 0.95}}, {}, 0)

        roster = {"a": {"description": "A", "excerpt": ""}}
        self.assertIsNone(sug.suggest("what is 2+2", roster, fake))
        self.assertEqual(len(calls), 1)

    def test_suggest_winner_when_it_fits(self):
        def fake(state, questions, tag=None, timeout=None):
            if "skill" in questions:
                return ({"skill": {"type": "choice", "choice": "a", "probabilities": {"a": 0.6, "b": 0.3, "c": 0.1}},
                         "acts_on_user_system": {"noul": 0.9}, "would_follow_documented_procedure": {"noul": 0.8},
                         "prose_suffices": {"noul": 0.1}}, {}, 0)
            return ({"winner": {"type": "choice", "choice": "b"}, "fits_0": {"noul": 0.2},
                     "fits_1": {"noul": 0.8}, "fits_2": {"noul": 0.1}}, {}, 0)

        roster = {k: {"description": k.upper(), "excerpt": ""} for k in "abc"}
        self.assertEqual(sug.suggest("transcribe this video", roster, fake), "b")

    def test_confident_wide_pick_bypasses_gate(self):
        # Tuned 2026-09-19 from the decision log: "should this pipeline be a durable workflow" ranked
        # temporal at 0.99 but the gate (0.27) dropped it because the prompt was phrased as a question.
        def fake(state, questions, tag=None, timeout=None):
            if "skill" in questions:
                return ({"skill": {"type": "choice", "choice": "a", "confidence": 0.99, "probabilities": {"a": 0.99}},
                         "acts_on_user_system": {"noul": 0.15}, "would_follow_documented_procedure": {"noul": 0.33},
                         "prose_suffices": {"noul": 0.67}}, {}, 0)
            return ({"winner": {"type": "choice", "choice": "a"}, "fits_0": {"noul": 0.9}}, {}, 0)

        self.assertEqual(sug.suggest("x" * 30, {"a": {"description": "A", "excerpt": ""}}, fake), "a")

    def test_suggest_nothing_when_no_candidate_fits(self):
        def fake(state, questions, tag=None, timeout=None):
            if "skill" in questions:
                return ({"skill": {"type": "choice", "choice": "a", "probabilities": {"a": 1}},
                         "acts_on_user_system": {"noul": 0.9}, "would_follow_documented_procedure": {"noul": 0.9},
                         "prose_suffices": {"noul": 0.0}}, {}, 0)
            return ({"winner": {"type": "choice", "choice": "a"}, "fits_0": {"noul": 0.1}}, {}, 0)

        self.assertIsNone(sug.suggest("x" * 30, {"a": {"description": "A", "excerpt": ""}}, fake))


class OptIn(unittest.TestCase):
    def test_off_unless_set_to_1(self):
        self.assertFalse(sug.enabled({}))
        self.assertFalse(sug.enabled({"JEV_SKILL_SUGGEST": "0"}))
        self.assertFalse(sug.enabled({"JEV_SKILL_SUGGEST": "yes"}))
        self.assertTrue(sug.enabled({"JEV_SKILL_SUGGEST": "1"}))

    def test_main_sends_nothing_when_not_enabled(self):
        from unittest import mock
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("JEV_SKILL_SUGGEST", None)
            with mock.patch.object(sug, "load_jev", side_effect=AssertionError("must not load jev")):
                sug.main(["please refactor the billing module for me"])


if __name__ == "__main__":
    unittest.main()
