"""Tests for bin/jev-skill-suggest policy (Jev stubbed, no network)."""
import json
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


class ParkedAgentTest(unittest.TestCase):
    """Parked agents (~/.claude/agents-parked/*.md) are ranked next to skills under an `agent:` key."""

    def make(self, d):
        os.makedirs(d)
        with open(os.path.join(d, "debugger.md"), "w") as f:
            f.write("---\nname: debugger\ndescription: Root-cause analysis.\n---\nYou debug things.")
        with open(os.path.join(d, "junk.md"), "w") as f:
            f.write("no frontmatter")

    def test_discovers_agents_from_dir(self):
        with tempfile.TemporaryDirectory() as d:
            agents = os.path.join(d, "agents-parked")
            self.make(agents)
            roster = sug._roster_from([], sug.agent_files(parked_dir=agents))
        self.assertEqual(list(roster), ["agent:debugger"])
        self.assertEqual(roster["agent:debugger"]["agent"], os.path.join(agents, "debugger.md"))
        self.assertIn("You debug things.", roster["agent:debugger"]["excerpt"])

    def test_agent_hint_says_delegate(self):
        roster = {"agent:debugger": {"description": "x", "excerpt": "", "agent": "/p/debugger.md"}}
        self.assertEqual(
            sug.hint("agent:debugger", roster),
            "<skill_relevance>Relevant agent: debugger. It is parked: delegate with "
            "`jdelegate --role debugger ...` (or read ~/.claude/agents-parked/debugger.md and follow it)."
            "</skill_relevance>")

    def test_skill_hints_unchanged_by_agents(self):
        roster = {"tdd": {"description": "x", "excerpt": ""}}
        self.assertIn("Relevant to the current request: tdd.", sug.hint("tdd", roster))

    def test_suggest_returns_agent_key_in_same_two_rounds(self):
        calls = []

        def fake(state, questions, tag=None, timeout=None):
            calls.append(questions)
            if "skill" in questions:
                self.assertIn("agent:debugger", questions["skill"]["criteria"])
                return ({"skill": {"type": "choice", "choice": "agent:debugger",
                                   "probabilities": {"agent:debugger": 0.8, "tdd": 0.2}},
                         "acts_on_user_system": {"noul": 0.9}, "would_follow_documented_procedure": {"noul": 0.8},
                         "prose_suffices": {"noul": 0.1}}, {}, 0)
            return ({"winner": {"type": "choice", "choice": "agent:debugger"}, "fits_0": {"noul": 0.9},
                     "fits_1": {"noul": 0.1}}, {}, 0)

        roster = {"agent:debugger": {"description": "D", "excerpt": "", "agent": "/p/debugger.md"},
                  "tdd": {"description": "T", "excerpt": ""}}
        self.assertEqual(sug.suggest("find the root cause of this crash", roster, fake), "agent:debugger")
        self.assertEqual(len(calls), 2)

    def test_main_name_mode_prints_agent_prefix(self):
        import io
        from contextlib import redirect_stdout

        roster = {"agent:debugger": {"description": "D", "excerpt": "", "agent": "/p/debugger.md"}}

        class J:
            JevError = RuntimeError
            ask_many = None

        old = (sug.cached_roster, sug.load_jev, sug.suggest, sug.SUGGEST_CACHE)
        tmp = tempfile.TemporaryDirectory()
        try:
            sug.SUGGEST_CACHE = os.path.join(tmp.name, "cache.json")
            sug.cached_roster = lambda: roster
            sug.load_jev = lambda: J
            sug.suggest = lambda *a, **k: "agent:debugger"
            buf = io.StringIO()
            with redirect_stdout(buf):
                sug.main(["--name", "find the root cause of this crash"])
            self.assertEqual(buf.getvalue().strip(), "agent:debugger")
            buf = io.StringIO()
            with redirect_stdout(buf):
                sug.main(["find the root cause of this crash"])
            self.assertIn("jdelegate --role debugger", buf.getvalue())
        finally:
            sug.cached_roster, sug.load_jev, sug.suggest, sug.SUGGEST_CACHE = old
            tmp.cleanup()


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

    def test_winner_needs_its_own_fits_score_not_another_candidates(self):
        def fake(state, questions, tag=None, timeout=None):
            if "skill" in questions:
                return ({"skill": {"type": "choice", "choice": "a", "probabilities": {"a": 0.6, "b": 0.3}},
                         "acts_on_user_system": {"noul": 0.9}, "would_follow_documented_procedure": {"noul": 0.9},
                         "prose_suffices": {"noul": 0.0}}, {}, 0)
            return ({"winner": {"type": "choice", "choice": "a"}, "fits_0": {"noul": 0.3}, "fits_1": {"noul": 0.95}}, {}, 0)

        roster = {k: {"description": k.upper(), "excerpt": ""} for k in "ab"}
        self.assertIsNone(sug.suggest("transcribe this video", roster, fake))

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


def wide_and_rerank(gate=0.9, conf=0.5, fit=0.95, pick="a"):
    """A fake ask_many whose gate mean, wide confidence and winner fit are chosen by the test."""
    calls = []

    def fake(state, questions, tag=None, timeout=None):
        calls.append(questions)
        if "skill" in questions:
            return ({"skill": {"type": "choice", "choice": pick, "confidence": conf, "probabilities": {pick: conf}},
                     "acts_on_user_system": {"noul": gate}, "would_follow_documented_procedure": {"noul": gate},
                     "prose_suffices": {"noul": 1 - gate}}, {}, 0)
        return ({"winner": {"type": "choice", "choice": pick}, "fits_0": {"noul": fit}}, {}, 0)

    fake.calls = calls
    return fake


ROSTER = {"a": {"description": "A", "excerpt": ""}}


class ThresholdTest(unittest.TestCase):
    """Thresholds fitted 2026-10-02 on 738 labelled skill-suggest outcomes (12 followed)."""

    def test_constants(self):
        self.assertEqual(sug.GATE_THRESHOLD, 0.6)
        self.assertEqual(sug.FITS_THRESHOLD, 0.8)
        self.assertEqual(sug.WIDE_BYPASS_CONFIDENCE, 0.99)

    def test_fit_below_threshold_is_dropped(self):
        self.assertIsNone(sug.suggest("x" * 30, ROSTER, wide_and_rerank(fit=0.7)))

    def test_fit_above_threshold_is_kept(self):
        self.assertEqual(sug.suggest("x" * 30, ROSTER, wide_and_rerank(fit=0.85)), "a")

    def test_gate_below_threshold_is_dropped(self):
        self.assertIsNone(sug.suggest("x" * 30, ROSTER, wide_and_rerank(gate=0.5, conf=0.95)))

    def test_bypass_needs_near_certain_pick(self):
        self.assertEqual(sug.suggest("x" * 30, ROSTER, wide_and_rerank(gate=0.2, conf=0.995)), "a")


class SkipTest(unittest.TestCase):
    def test_follow_ups_are_skipped(self):
        for p in ("ok continue", "yes", "continue", "go", "?", "نعم", "كمل", "oui", "d'accord", "ok", "no",
                  "fix this please", "/kb-query the whole thing please", "OK  Continue ", "continue please go on now"):
            self.assertTrue(sug.is_follow_up(p), p)

    def test_real_prompts_are_not_skipped(self):
        for p in ("fix the login bug in the payment API", "make the pricing page responsive on mobile"):
            self.assertFalse(sug.is_follow_up(p), p)


class CacheAndSessionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = (sug.SUGGEST_CACHE, sug.HOOK_SEEN, sug.cached_roster, sug.load_jev, sug.load_usage)
        sug.SUGGEST_CACHE = os.path.join(self.tmp.name, "suggest-cache.json")
        sug.HOOK_SEEN = os.path.join(self.tmp.name, "seen")
        self.fake = wide_and_rerank()

        class J:
            JevError = RuntimeError
            ask_many = staticmethod(self.fake)

        sug.cached_roster = lambda: ROSTER
        sug.load_jev = lambda: J
        sug.load_usage = lambda: {}

    def tearDown(self):
        sug.SUGGEST_CACHE, sug.HOOK_SEEN, sug.cached_roster, sug.load_jev, sug.load_usage = self.old
        self.tmp.cleanup()

    def run_main(self, argv):
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            sug.main(argv)
        return buf.getvalue()

    def test_short_and_ack_prompts_make_zero_jev_calls(self):
        for p in ("ok continue", "yes", "نعم", "go ahead now"):
            self.assertEqual(self.run_main([p]), "")
        self.assertEqual(len(self.fake.calls), 0)

    def test_same_normalized_prompt_hits_cache(self):
        out1 = self.run_main(["--name", "Fix the login   bug in the API"])
        n = len(self.fake.calls)
        self.assertEqual(out1.strip(), "a")
        self.assertEqual(n, 2)
        out2 = self.run_main(["--name", "fix the login bug in the api"])
        self.assertEqual(out2.strip(), "a")
        self.assertEqual(len(self.fake.calls), n)

    def test_negative_result_is_cached_too(self):
        self.fake = wide_and_rerank(fit=0.1)
        sug.load_jev = lambda f=self.fake: type("J", (), {"JevError": RuntimeError, "ask_many": staticmethod(f)})
        self.run_main(["fix the login bug in the API"])
        self.run_main(["fix the login bug in the API"])
        self.assertEqual(len(self.fake.calls), 2)

    def test_expired_cache_entry_is_ignored(self):
        import time
        sug.cache_put("fix the login bug in the api", "a")
        with open(sug.SUGGEST_CACHE) as f:
            c = json.load(f)
        c["fix the login bug in the api"]["ts"] = time.time() - 700
        with open(sug.SUGGEST_CACHE, "w") as f:
            json.dump(c, f)
        self.assertEqual(sug.cache_get("fix the login bug in the api"), (False, None))

    def test_cache_is_capped(self):
        for i in range(sug.CACHE_MAX + 20):
            sug.cache_put(f"prompt number {i}", "a")
        with open(sug.SUGGEST_CACHE) as f:
            self.assertEqual(len(json.load(f)), sug.CACHE_MAX)

    def test_one_hint_per_skill_per_session(self):
        first = self.run_main(["--session", "s1", "fix the login bug in the API"])
        self.assertIn("skill_relevance", first)
        again = self.run_main(["--session", "s1", "now fix the billing bug in the API"])
        self.assertEqual(again, "")
        other = self.run_main(["--session", "s2", "now fix the billing bug in the API"])
        self.assertIn("skill_relevance", other)

    def test_cached_result_respects_session_dedupe(self):
        self.run_main(["--session", "s1", "fix the login bug in the API"])
        self.assertEqual(self.run_main(["--session", "s1", "fix the login bug in the API"]), "")


if __name__ == "__main__":
    unittest.main()
