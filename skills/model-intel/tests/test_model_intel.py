import csv, json, os, re, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL / "scripts"))
FX = SKILL / "tests" / "fixtures"
import mi, fetch, diff, recommend, propose_tiers, render_picks  # noqa: E402


def write_rows(path, rows, cols):
    mi.write_csv(path, rows, cols)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="mi-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.data = self.tmp / "data"
        self.data.mkdir()
        mi.DATA = self.data
        self.tiers = self.tmp / "tiers.json"
        mi.TIERS = self.tiers
        self.pi = self.tmp / "pi"
        self.pi.mkdir()
        recommend.PI = self.pi
        os.environ["MODEL_INTEL_DATE"] = "2026-10-11"
        os.environ["MODEL_INTEL_VALIDATE_CMD"] = "true"

    def fetch_fixture(self, date="2026-10-11", from_dir=FX):
        os.environ["MODEL_INTEL_DATE"] = date
        return fetch.main(["--from-dir", str(from_dir)])

    def base_tiers(self):
        t = {"_comment": ["2026-10-07 owner: kinds.language is Arabic-only (GPT-6 Luna first)"],
             "metered_providers": ["openrouter"], "thinking": {"T2": "low", "T3": "medium", "T4": "high"},
             "tiers": {"T3": ["cliproxy/claude-sonnet-5-5", "opencode-go/mimo-v2.6-pro"], "T4": ["cliproxy/claude-sonnet-5-5"]},
             "kinds": {"language": {"T3": ["commandcode/gpt-6-luna"]}},
             "orchestrator": ["cliproxy/claude-opus-5-5"], "_blocked": {}}
        self.tiers.write_text(json.dumps(t, indent=2))
        return t


class FetchParse(Base):
    def test_llm_fixture(self):
        rows = fetch.parse_llm((FX / "llm.html").read_text())
        self.assertEqual(len(rows), 10)
        by = {r["slug"]: r for r in rows}
        self.assertEqual(by["claude-opus-5-5-high"]["effort_mode"], "high")
        self.assertEqual(by["claude-opus-5-5-high"]["base_model"], "Claude Opus 5.5")
        self.assertEqual(by["gpt-6-luna"]["release_date"] != "", True)
        r = by["gpt-6-1-sol"]
        self.assertAlmostEqual(r["blended_price_3to1_per_1M"], (3 * 2 + 10) / 4)
        self.assertGreater(float(r["intelligence_index"]), 40)
        self.assertNotEqual(r["cost_per_task_usd"], "")

    def test_media_and_stt_fixtures(self):
        t2i = fetch.PARSERS["text-to-image.html"]((FX / "text-to-image.html").read_text())
        self.assertEqual(len(t2i), 5)
        self.assertEqual(t2i[0]["rank"], 1)
        self.assertEqual(t2i[0]["score_kind"], "elo")
        self.assertGreater(float(t2i[0]["score"]), float(t2i[-1]["score"]))
        stt = fetch.parse_stt((FX / "stt.html").read_text())
        self.assertGreaterEqual(len(stt), 4)
        self.assertEqual(stt[0]["rank"], 1)
        self.assertLessEqual(float(stt[0]["score"]), float(stt[1]["score"]))

    def test_fetch_writes_snapshot_and_latest(self):
        self.assertEqual(self.fetch_fixture(), 0)
        self.assertTrue((self.data / "latest").is_symlink())
        self.assertEqual(len(mi.read_csv(self.data / "latest" / "llm.csv")), 10)
        for f in mi.MEDIA_FILES:
            self.assertTrue((self.data / "latest" / f).exists(), f)


class RowDrop(Base):
    def test_drop_over_30pct_keeps_previous_latest(self):
        self.assertEqual(self.fetch_fixture("2026-10-04"), 0)
        small = self.tmp / "small"
        shutil.copytree(FX, small)
        # keep 3 of the 10 LLM models: a 70% drop
        import re
        html = (small / "llm.html").read_text()
        keep = {"claude-opus-5-5", "claude-sonnet-5-5", "gpt-6-luna"}
        objs = list(fetch.iter_objs(mi.rsc_text(html), "intelligenceIndex"))
        txt = "".join(json.dumps(o) for o in objs if o["slug"] in keep)
        (small / "llm.html").write_text("<script>self.__next_f.push([1,%s])</script>" % json.dumps(txt))
        before = (self.data / "latest").resolve()
        rc = self.fetch_fixture("2026-10-11", small)
        self.assertEqual(rc, 1)
        self.assertEqual((self.data / "latest").resolve(), before)
        self.assertFalse((self.data / "snapshots" / "2026-10-11").exists())
        self.assertEqual(len(mi.read_csv(before / "llm.csv")), 10)

    def test_empty_parse_fails(self):
        bad = self.tmp / "bad"
        shutil.copytree(FX, bad)
        (bad / "tts.html").write_text("<html>redesigned</html>")
        self.assertEqual(self.fetch_fixture(from_dir=bad), 1)
        self.assertFalse((self.data / "latest").exists())


class Diff(Base):
    def test_new_removed_changed(self):
        self.assertEqual(self.fetch_fixture("2026-10-04"), 0)
        self.fetch_fixture("2026-10-11")
        cur = self.data / "snapshots" / "2026-10-11"
        rows = mi.read_csv(cur / "llm.csv")
        gone = rows.pop(0)
        rows[0]["intelligence_index"] = str(float(rows[0]["intelligence_index"]) * 1.2)   # +20%
        rows[1]["output_tokens_per_s"] = str(float(rows[1]["output_tokens_per_s"]) * 1.02)  # +2%, ignored
        rows.append(dict(rows[0], slug="brand-new", model="Brand New"))
        write_rows(cur / "llm.csv", rows, mi.LLM_COLS)
        d = diff.compute(self.data / "snapshots" / "2026-10-04", cur)
        self.assertEqual([x["slug"] for x in d["llm"]["new"]], ["brand-new"])
        self.assertEqual([x["slug"] for x in d["llm"]["removed"]], [gone["slug"]])
        fields = {(c["slug"], c["field"]) for c in d["llm"]["changed"]}
        self.assertIn((rows[0]["slug"], "index"), fields)
        self.assertNotIn((rows[1]["slug"], "tok/s"), fields)
        self.assertIn("Brand New", diff.render(d))


class Recommend(Base):
    def test_reachable_and_picks(self):
        self.base_tiers()
        (self.pi / "models-store.json").write_text(json.dumps({
            "openai-codex": {"models": [{"id": "gpt-6.1-sol"}, {"id": "gpt-6-luna"}]},
            "openrouter": {"models": [{"id": "anthropic/claude-haiku-5.5"}]},
            "opencode-go": {"models": [{"id": "mimo-v2.6-pro"}]}}))
        (self.pi / "models.json").write_text(json.dumps({"providers": {"cliproxy": {"models": [
            {"id": "claude-opus-5-5"}, {"id": "claude-sonnet-5-5"}, {"id": "claude-haiku-5-5"}]}}}))
        self.fetch_fixture()
        reach = recommend.build_reachable()
        m = reach["models"]
        self.assertEqual(m["gpt61sol"]["best_provider"], "openai-codex")
        self.assertTrue(m["gpt61sol"]["subscription"])
        self.assertEqual(m["claudehaiku55"]["best_provider"], "cliproxy")  # subscription ranked before openrouter
        rows = recommend.load_llm(reach)
        uc = {name: r for name, _, r, _, _ in recommend.usecases(rows)}
        self.assertEqual(uc["Arabic copy (GPT first)"]["creator"], "OpenAI")
        self.assertIsNone(uc["Arabic copy (Gemini fallback)"])  # no Gemini reachable in this fixture
        self.assertEqual(uc["Main coding"]["key"], "claudeopus55")       # owner pin
        self.assertEqual(uc["Main coding"]["effort"], "high")
        self.assertEqual(uc["Orchestration"]["effort"], "high")
        self.assertIsNone(uc["Architecture"])                           # no xhigh score in this fixture
        self.assertEqual(uc["Plans / review / second opinion"]["creator"], "OpenAI")
        for name, r in uc.items():
            self.assertTrue(r is None or r["effort"] != "max", name)   # F13: never max
        md = recommend.render(reach)
        self.assertIn("PixVerse", md)
        self.assertIn("overlay", md)
        self.assertIn("best value: stop here", md)


class RenderPicks(Base):
    def test_writes_header_jev_judging_and_effort_rule(self):
        self.base_tiers()
        (self.pi / "models.json").write_text(json.dumps({"providers": {"cliproxy": {"models": [
            {"id": "claude-opus-5-5"}, {"id": "claude-haiku-5-5"}]}}}))
        self.fetch_fixture()
        out = self.tmp / "ref" / "model-picks.md"
        os.environ["MODEL_PICKS_OUT"] = str(out)
        self.addCleanup(os.environ.pop, "MODEL_PICKS_OUT", None)
        self.assertEqual(render_picks.main(), 0)
        md = out.read_text()
        self.assertIn("Generated by model-intel (weekly). Do not edit by hand.", md)
        self.assertIn("https://claude.ai/artifact/", md)
        self.assertTrue(any(l.startswith("| Judging |") and "Jev" in l for l in md.splitlines()))
        self.assertIn("## Effort rule", md)


def row(key, base, effort, index, cost, tps, creator="Z", sub=True, providers=None):
    prov = providers or [{"provider": "opencode-go", "id": f"opencode-go/{key}", "subscription": sub, "source": "t"}]
    return {"model": base, "base": base, "effort": effort, "slug": key, "key": key, "creator": creator, "index": index,
            "cost": cost, "tps": tps, "price_in": 1, "price_out": 2,
            "reach": {"providers": prov, "best_provider": prov[0]["provider"], "subscription": any(p["subscription"] for p in prov)}}


class AutoApply(Base):
    def setUp(self):
        super().setUp()
        self.t = self.base_tiers()
        self.inc = row("mimoold", "Mimo Old", "medium", 40.0, 0.50, 100, "Xiaomi")
        chain = ["cliproxy/claude-sonnet-5-5", "opencode-go/mimo-old"]
        self.t["tiers"] = {"T3": list(chain)}
        self.t["kinds"] = {"general": {"T3": list(chain)}, "language": {"T3": ["commandcode/gpt-6-luna"]}}

    def go(self, cand, probe=lambda m: True, tiers=None):
        rows = [self.inc, cand]
        reach = {"models": {r["key"]: r["reach"] for r in rows}}
        return propose_tiers.decide(tiers or self.t, rows, reach, probe)

    def chains(self, items):
        return {a["chain"] for a in items}

    def test_applies_when_all_conditions_hold(self):
        auto, props = self.go(row("newmodel", "New Model", "medium", 42.5, 0.40, 90))
        self.assertEqual(self.chains(auto), {"tiers.T3", "kinds.general.T3"})
        self.assertEqual(auto[0]["insert"], "opencode-go/newmodel")

    def test_equal_index_needs_70pct_cost(self):
        auto, _ = self.go(row("newmodel", "New Model", "medium", 40.1, 0.34, 100))
        self.assertTrue(auto)
        auto, props = self.go(row("newmodel", "New Model", "medium", 40.1, 0.40, 100))
        self.assertFalse(auto)

    def test_not_applied_cases(self):
        for cand, why in [
            (row("m1", "M", "medium", 41.5, 0.40, 90), "gain < 2"),
            (row("m2", "M", "medium", 45.0, 0.60, 90), "dearer"),
            (row("m3", "M", "medium", 45.0, 0.40, 90, sub=False, providers=[
                {"provider": "openrouter", "id": "openrouter/m3", "subscription": False, "source": "t"}]), "metered only"),
            (row("m4", "M", "medium", 45.0, 0.40, 30), "much slower"),
        ]:
            auto, props = self.go(cand)
            self.assertFalse(auto, why)
        auto, props = self.go(row("m3", "M", "medium", 45.0, 0.40, 90, providers=[
            {"provider": "openrouter", "id": "openrouter/m3", "subscription": False, "source": "t"}]))
        self.assertFalse(auto)
        self.assertIn("metered-only", props[0]["reason"])

    def test_probe_failure_goes_to_proposals(self):
        auto, props = self.go(row("newmodel", "New Model", "medium", 45.0, 0.40, 90), probe=lambda m: False)
        self.assertFalse(auto)
        self.assertTrue(any("probe failed" in p["reason"] for p in props))

    def test_pinned_and_owner_rules(self):
        auto, props = self.go(row("newmodel", "New Model", "medium", 45.0, 0.40, 90, creator="OpenAI"))
        self.assertEqual(self.chains(auto), set())            # GPT never enters general/implementer chains
        auto, props = self.go(row("newgpt", "New GPT", "medium", 60.0, 0.01, 90, creator="OpenAI"))
        self.assertNotIn("kinds.language.T3", self.chains(auto))   # pinned by the owner comment
        self.assertFalse(any(a["chain"].startswith("kinds.language") for a in auto))

    def test_already_in_tiers_is_not_auto(self):
        self.t["tiers"]["T3"].append("opencode-go/newmodel")
        auto, props = self.go(row("newmodel", "New Model", "medium", 45.0, 0.40, 90))
        self.assertNotIn("tiers.T3", self.chains(auto))

    def test_apply_backs_up_inserts_and_keeps_claude(self):
        self.tiers.write_text(json.dumps(self.t, indent=2))
        auto, _ = self.go(row("newmodel", "New Model", "medium", 45.0, 0.40, 90))
        backup = propose_tiers.apply_changes(self.tiers, auto, "2026-10-11")
        self.assertTrue(backup.exists())
        self.assertEqual(json.loads(backup.read_text())["tiers"]["T3"],
                         ["cliproxy/claude-sonnet-5-5", "opencode-go/mimo-old"])
        new = json.loads(self.tiers.read_text())
        self.assertEqual(new["tiers"]["T3"], ["cliproxy/claude-sonnet-5-5", "opencode-go/newmodel", "opencode-go/mimo-old"])
        self.assertIn("model-intel auto-apply", new["_comment"][-1])
        self.assertEqual(subprocess.run(["jq", "empty", str(self.tiers)]).returncode, 0)

    def test_failed_validation_restores_backup(self):
        os.environ["MODEL_INTEL_VALIDATE_CMD"] = "false"
        self.tiers.write_text(json.dumps(self.t, indent=2))
        orig = self.tiers.read_text()
        auto, _ = self.go(row("newmodel", "New Model", "medium", 45.0, 0.40, 90))
        with self.assertRaises(RuntimeError):
            propose_tiers.apply_changes(self.tiers, auto, "2026-10-11")
        self.assertEqual(self.tiers.read_text(), orig)

    def test_cli_end_to_end_on_temp_copy(self):
        self.fetch_fixture()
        cur = self.data / "snapshots" / "2026-10-11"
        rows = mi.read_csv(cur / "llm.csv")
        rows.append(dict(next(r for r in rows if r["slug"] == "claude-sonnet-5-5-high"),
                         slug="testmodel-x-high", model="Test Model X (High)", base_model="Test Model X",
                         effort_mode="high", creator="Acme", intelligence_index="55.0", cost_per_task_usd="0.10",
                         output_tokens_per_s="120"))
        write_rows(cur / "llm.csv", rows, mi.LLM_COLS)
        t = self.base_tiers()
        t["thinking"]["T3"] = "high"
        t["tiers"] = {"T3": ["cliproxy/claude-sonnet-5-5", "opencode-go/mimo-v2.6-pro"]}
        t["kinds"] = {}
        self.tiers.write_text(json.dumps(t, indent=2))
        (self.pi / "models-store.json").write_text(json.dumps({"opencode-go": {"models": [{"id": "testmodel-x"}]}}))
        env = dict(os.environ, MODEL_INTEL_DATA=str(self.data), MODEL_INTEL_TIERS=str(self.tiers),
                   MODEL_INTEL_PI_DIR=str(self.pi), MODEL_INTEL_PROBE="ok", MODEL_INTEL_VALIDATE_CMD="true",
                   MODEL_INTEL_DATE="2026-10-11")
        r = subprocess.run([sys.executable, "-I", str(SKILL / "scripts/propose_tiers.py")], env=env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertEqual(json.loads(self.tiers.read_text())["tiers"]["T3"],
                         ["cliproxy/claude-sonnet-5-5", "opencode-go/testmodel-x", "opencode-go/mimo-v2.6-pro"])
        self.assertTrue((self.tmp / "tiers.json.bak-model-intel-2026-10-11").exists())
        self.assertTrue((self.data / "proposals" / "2026-10-11.md").exists())
        env["MODEL_INTEL_PROBE"] = "fail"
        self.tiers.write_text(json.dumps(t, indent=2))
        r = subprocess.run([sys.executable, "-I", str(SKILL / "scripts/propose_tiers.py")], env=env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(json.loads(self.tiers.read_text())["tiers"]["T3"],
                         ["cliproxy/claude-sonnet-5-5", "opencode-go/mimo-v2.6-pro"])

    # F15: pins are entries, not tier sections: a qualifying model lands in a free T3 slot, never a pinned one.
    def test_unpinned_t3_slot_is_auto_applied_on_temp_copy(self):
        self.t["tiers"] = {"T3": ["cliproxy/claude-sonnet-5-5", "opencode-go/mimo-old"],
                           "T4": ["cliproxy/claude-sonnet-5-5", "cliproxy/claude-opus-5-5", "opencode-go/mimo-old"]}
        self.t["kinds"] = {}
        self.tiers.write_text(json.dumps(self.t, indent=2))
        auto, _ = self.go(row("newmodel", "New Model", "medium", 45.0, 0.40, 90))
        self.assertEqual(self.chains(auto), {"tiers.T3", "tiers.T4"})
        propose_tiers.apply_changes(self.tiers, auto, "2026-10-11")
        new = json.loads(self.tiers.read_text())
        self.assertEqual(new["tiers"]["T3"], ["cliproxy/claude-sonnet-5-5", "opencode-go/newmodel", "opencode-go/mimo-old"])
        self.assertEqual(new["tiers"]["T4"][:2], ["cliproxy/claude-sonnet-5-5", "cliproxy/claude-opus-5-5"])
        self.assertEqual(new["tiers"]["T4"][2], "opencode-go/newmodel")

    def test_pinned_slot_is_never_auto_applied(self):
        sonnet = row("claudesonnet55", "Claude Sonnet 5.5", "medium", 40.0, 0.50, 100, "Anthropic",
                     providers=[{"provider": "cliproxy", "id": "cliproxy/claude-sonnet-5-5", "subscription": True, "source": "t"}])
        cand = row("newmodel", "New Model", "medium", 55.0, 0.10, 100)
        self.t["tiers"] = {"T3": ["cliproxy/claude-sonnet-5-5"]}
        self.t["kinds"] = {}
        rows = [sonnet, cand]
        auto, props = propose_tiers.decide(self.t, rows, {"models": {r["key"]: r["reach"] for r in rows}}, lambda m: True)
        self.assertEqual(auto, [])
        self.assertIn("owner-pinned entry", props[0]["reason"])

    def test_tier_sections_are_not_pinned_but_owner_chains_are(self):
        self.t["_comment"] = ["2026-10-03 owner: T2 T3 T4 chains re-ordered; kinds.language is Arabic-only"]
        pins = propose_tiers.pinned(self.t)
        for sec in ("tiers.T2", "tiers.T3", "tiers.T4"):
            self.assertNotIn(sec, pins)
        self.assertIn("kinds.language", pins)
        self.assertEqual(propose_tiers.pinned_prefix(["cliproxy/claude-sonnet-5-5", "cliproxy/claude-opus-5-5", "x/y"], "T4"), 2)
        self.assertEqual(propose_tiers.pinned_prefix(["cliproxy/claude-haiku-5-5", "x/y"], "T2"), 0)


def fam(key, base, creator, spec, prov="opencode-go"):
    """spec: [(effort, index, cost, tps)]"""
    p = [{"provider": prov, "id": f"{prov}/{key}", "subscription": True, "source": "t"}]
    return [row(key, base, e, i, c, t, creator, providers=p) for e, i, c, t in spec]


class F12F13(Base):
    def rows(self):
        r = []
        r += fam("claudehaiku55", "Claude Haiku 5.5", "Anthropic",
                 [("low", 29.45, 0.024, 178), ("medium", 34.5, 0.047, 166), ("high", 37.8, 0.079, 174),
                  ("xhigh", 41.25, 0.124, 188), ("max", 43.4, 0.213, 240)], "cliproxy")
        r += fam("claudeopus55", "Claude Opus 5.5", "Anthropic",
                 [("medium", 51.2, 1.34, 75), ("high", 53.6, 1.82, 76), ("xhigh", 56.0, 3.46, 80), ("max", 57.6, 5.98, 96)], "cliproxy")
        r += fam("slowcheap", "Slow Cheap", "Xiaomi", [("default", 46.3, 0.133, 43)])
        r += fam("fastpricey", "Fast Pricey", "Meta", [("xhigh", 45.0, 1.37, 280)])
        r += fam("gpt61sol", "GPT-6.1 Sol", "OpenAI", [("medium", 47.8, 0.21, 49), ("high", 50.2, 0.32, 50),
                                                      ("max", 51.8, 0.72, 55)], "openai-codex")
        r += fam("gemini38flash", "Gemini 3.8 Flash", "Google", [("low", 33.45, 0.5, 100), ("medium", 39.8, 0.93, 110),
                                                               ("high", 40.9, 1.24, 125)], "commandcode")
        r += fam("newtop", "New Top", "Acme", [("high", 56.5, 2.0, 90)])
        return r

    def test_effort_rule_lowest_within_tolerance_never_max(self):
        rows = self.rows()
        pick = lambda k, **kw: recommend.effort_pick([r for r in rows if r["key"] == k], **kw)
        self.assertEqual(pick("claudeopus55")["effort"], "xhigh")        # high is 2.4 below xhigh
        self.assertEqual(pick("claudeopus55", hardest=True)["effort"], "max")
        self.assertEqual(pick("gpt61sol")["effort"], "high")             # no xhigh: best non-max is the reference
        self.assertEqual(pick("gemini38flash")["effort"], "medium")      # 39.8 is within 1.5 of 40.9
        self.assertEqual(pick("claudehaiku55")["effort"], "xhigh")

    def test_use_case_objectives(self):
        uc = {n: r for n, _, r, _, _ in recommend.usecases(self.rows())}
        self.assertEqual((uc["Judging subagents"]["base"], uc["Judging subagents"]["effort"]), ("Claude Haiku 5.5", "xhigh"))
        self.assertEqual(uc["Search subagents"]["key"], "claudehaiku55")   # >= 100 tok/s preferred over slowcheap
        self.assertEqual(uc["Bulk cheap text"]["key"], "claudehaiku55")
        self.assertEqual(uc["Non-Claude fallback"]["key"], "slowcheap")    # best index per cost, index >= 44
        self.assertEqual(uc["Plans / review / second opinion"]["key"], "gpt61sol")
        self.assertEqual(uc["Plans / review / second opinion"]["effort"], "high")
        self.assertEqual(uc["Arabic copy (GPT first)"]["key"], "gpt61sol")
        self.assertEqual(uc["Arabic copy (Gemini fallback)"]["effort"], "medium")
        for n, r in uc.items():
            self.assertTrue(r is None or r["effort"] != "max", n)

    def test_judging_row_is_jev_first_haiku_pin(self):
        uc = {n: (r, obj, note) for n, _, r, obj, note in recommend.usecases(self.rows())}
        row, obj, note = uc["Judging subagents"]
        self.assertEqual(row["base"], "Claude Haiku 5.5")                 # Haiku is the fallback behind Jev
        self.assertIn("owner pin: Jev first, Haiku 5.5 fallback", obj)
        self.assertIn("owner pin: Jev first, Haiku 5.5 fallback", note)  # the note column is what the table renders

    def test_pins_hold_and_better_model_is_a_candidate(self):
        ucs = {n: (r, note) for n, _, r, _, note in recommend.usecases(self.rows())}
        main, note = ucs["Main coding"]
        self.assertEqual((main["key"], main["effort"]), ("claudeopus55", "high"))   # pin, not replaced
        self.assertIn("candidate (not applied): New Top", note)
        self.assertIn("F13 alone would pick xhigh", note)
        self.assertEqual(ucs["Architecture"][0]["effort"], "xhigh")


class KieReach(Base):
    CAT = {"built": "2026-10-11", "catalogue_date": "2026-08-07",
           "ids": ["bytedance/seedance-2", "bytedance/seedance-2-5", "gpt/gpt-image-2-text-to-image", "pixverse/text-to-video",
                   "google/nanobanana2", "google/pro-image-to-image", "seedream/5-pro-text-to-image", "wan/2-7-text-to-video"]}

    def test_aliases_match_version_not_just_family(self):
        ids = lambda n: recommend.kie_ids(n, self.CAT)
        self.assertEqual(ids("Dreamina Seedance 2.5"), ["bytedance/seedance-2-5"])
        self.assertEqual(ids("Dreamina Seedance 2.0 720p"), ["bytedance/seedance-2"])
        self.assertTrue(ids("GPT Image 2 (high)"))
        self.assertFalse(ids("GPT Image 2.5 Sunburst (max)"))
        self.assertFalse(ids("Wan 3.0"))
        self.assertTrue(ids("Wan2.7-260612"))
        self.assertFalse(ids("Nano Banana 2.1"))
        self.assertTrue(ids("Nano Banana 2 (Gemini 3.1 Flash Image)"))
        self.assertTrue(ids("PixVerse V6"))
        self.assertFalse(ids("Eleven v4 Turbo"))
        self.assertFalse(ids("Gemini 3.8 Flash TTS"))

    def test_every_alias_target_exists_in_the_built_catalogue(self):
        kie = recommend.build_kie()
        if not kie["ids"]:
            self.skipTest("no kie-ai catalogue on this machine")
        have_doc = recommend.KIE_EXTRA_DOC.exists()
        for name_re, id_re in recommend.KIE_ALIASES:
            if id_re == r"^veo-3-1$" and not have_doc:
                continue
            self.assertTrue(any(re.search(id_re, i) for i in kie["ids"]), f"{name_re} -> {id_re} not in catalogue")

    def test_media_rows_split_kie_best_from_global_leader(self):
        self.fetch_fixture()
        out = {n: (r, ids) for n, r, ids, _ in recommend.media_rows(self.CAT)}
        r, ids = out["Image text-to-image: best on Kie"]
        self.assertEqual(r["model"], "GPT Image 2 (high)")
        self.assertEqual(r["rank"], "3")
        lead, _ = out["Image text-to-image: global leader (not on Kie)"]
        self.assertTrue(lead["model"].startswith("GPT Image 2.5"))
        r, ids = out["Video text-to-video: best on Kie"]
        self.assertEqual(ids, ["bytedance/seedance-2-5"])
        self.assertEqual(out["Video text-to-video: global leader (not on Kie)"][0]["model"], "Wan 3.0")
        self.assertIsNone(out["TTS: best on Kie"][0])
        self.assertTrue([n for n in out if "not on Kie" in n])


if __name__ == "__main__":
    unittest.main()
