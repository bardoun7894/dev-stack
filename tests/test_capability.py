"""Tests for the capability layer: scan -> outcomes -> registry -> rerank state -> auto-park. Temp dirs only."""
import importlib.machinery
import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import time
import unittest
from datetime import datetime, timezone

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
PARK = os.path.join(ROOT, "scripts", "park-skills.sh")


def load_path(path, name):
    loader = importlib.machinery.SourceFileLoader(name, os.path.join(ROOT, path))
    spec = importlib.util.spec_from_loader(name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


scan = load_path("scripts/capability-scan.py", "capability_scan")
registry = load_path("scripts/capability-registry.py", "capability_registry")
outcomes = load_path("scripts/capability-outcomes.py", "capability_outcomes")
sug = load_path("bin/jev-skill-suggest", "jev_skill_suggest_cap")
jev = load_path("bin/jev", "jev_cap")


def iso(ts):
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def user(ts, text, session="s1", **kw):
    content = text if isinstance(text, str) else text
    return {"type": "user", "timestamp": iso(ts), "sessionId": session, "isSidechain": False,
            "message": {"role": "user", "content": content}, **kw}


def tool(ts, name, inp, session="s1"):
    return {"type": "assistant", "timestamp": iso(ts), "sessionId": session,
            "message": {"role": "assistant", "content": [{"type": "tool_use", "id": "t", "name": name, "input": inp}]}}


def tool_result(ts, session="s1"):
    return {"type": "user", "timestamp": iso(ts), "sessionId": session,
            "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t", "content": "ok"}]}}


def write_jsonl(path, rows, mode="w"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, mode) as f:
        for r in rows:
            f.write(json.dumps(r, separators=(",", ":")) + "\n")


def read_jsonl(path):
    with open(path) as f:
        return [json.loads(l) for l in f if l.strip()]


class Base(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.d = self.t.name
        self.proj = self.d + "/projects"
        self.state = self.d + "/state"
        self.now = time.time()
        self.old_log = os.environ.get("JEV_LOG_DIR")
        os.environ["JEV_LOG_DIR"] = self.d + "/jev"
        os.environ["JDELEGATE_CACHE_DIR"] = self.d + "/jd-none"

    def tearDown(self):
        self.t.cleanup()
        del os.environ["JDELEGATE_CACHE_DIR"]
        if self.old_log is None:
            del os.environ["JEV_LOG_DIR"]
        else:
            os.environ["JEV_LOG_DIR"] = self.old_log

    def transcript(self, rows, session="s1", project="-Users-me-code-app", mode="w"):
        p = f"{self.proj}/{project}/{session}.jsonl"
        write_jsonl(p, rows, mode)
        return p

    def usage(self):
        return read_jsonl(self.state + "/usage.jsonl")


class ScanTest(Base):
    def test_events_have_preceding_prompt_and_strip_system_reminders(self):
        t0 = self.now - 100
        self.transcript([
            user(t0, [{"type": "text", "text": "<system-reminder>noise</system-reminder>"},
                      {"type": "text", "text": "please deploy the app"}]),
            tool(t0 + 1, "Skill", {"skill": "deploy"}),
            tool_result(t0 + 2),
            tool(t0 + 3, "Read", {"file_path": "/h/.claude/skills-parked/video-use/SKILL.md"}),
            user(t0 + 10, "now plan it <system-reminder>x</system-reminder>"),
            tool(t0 + 11, "Bash", {"command": "cat ~/.claude/skills-parked/pdf/SKILL.md | head"}),
            tool(t0 + 12, "Agent", {"subagent_type": "planner", "prompt": "p"}),
            tool(t0 + 13, "mcp__github__create_issue", {"title": "x"}),
            tool(t0 + 14, "Bash", {"command": "ls"}),
        ])
        stats = scan.scan(self.proj, self.state)
        ev = {(e["kind"], e["name"]): e for e in self.usage()}
        self.assertEqual(stats["events"], 5)
        self.assertEqual(ev[("skill", "deploy")]["via"], "skill-tool")
        self.assertEqual(ev[("skill", "deploy")]["prompt"], "please deploy the app")
        self.assertEqual(ev[("skill", "video-use")]["via"], "parked-read")
        self.assertEqual(ev[("skill", "pdf")]["prompt"], "now plan it")
        self.assertEqual(ev[("agent", "planner")]["via"], "agent-tool")
        self.assertEqual(ev[("mcp", "github")]["via"], "mcp-tool")
        self.assertEqual(ev[("mcp", "github")]["session"], "s1")
        self.assertEqual(ev[("mcp", "github")]["project"], "-Users-me-code-app")
        self.assertIsInstance(ev[("mcp", "github")]["ts"], int)

    def test_nested_subagent_transcript_found_and_attributed_to_parent_session(self):
        t0 = self.now - 100
        self.transcript([user(t0, "do the thing please", session="parent-1"),
                         tool(t0 + 1, "Skill", {"skill": "a"}, session="parent-1")], session="parent-1")
        sub = f"{self.proj}/-Users-me-code-app/parent-1/subagents/agent-abc.jsonl"
        row = tool(t0 + 5, "Skill", {"skill": "test-driven-development"})
        row.pop("sessionId")
        row["isSidechain"] = True
        write_jsonl(sub, [{"type": "user", "isSidechain": True, "timestamp": iso(t0 + 4),
                           "message": {"role": "user", "content": "subagent brief text"}}, row])
        stats = scan.scan(self.proj, self.state)
        ev = {e["name"]: e for e in self.usage()}
        self.assertEqual(stats["events"], 2)
        self.assertEqual(stats["turns"], 1)  # the subagent brief is not a user turn
        self.assertEqual(ev["test-driven-development"]["session"], "parent-1")
        self.assertEqual(ev["test-driven-development"]["project"], "-Users-me-code-app")
        self.assertTrue(ev["test-driven-development"]["sub"])
        self.assertNotIn("sub", ev["a"])

    def test_every_skill_call_in_a_multi_block_line_counts(self):
        t0 = self.now - 100
        row = tool(t0 + 1, "Skill", {"skill": "a"})
        row["message"]["content"] += [{"type": "text", "text": "hi"},
                                      {"type": "tool_use", "id": "u", "name": "Skill", "input": {"skill": "b"}},
                                      {"type": "tool_use", "id": "v", "name": "Skill", "input": {"skill": "c"}}]
        self.transcript([user(t0, "go go go go"), row])
        scan.scan(self.proj, self.state)
        self.assertEqual(sorted(e["name"] for e in self.usage()), ["a", "b", "c"])

    def test_long_prompt_truncated_to_300(self):
        self.transcript([user(self.now - 5, "x" * 500), tool(self.now - 4, "Skill", {"skill": "a"})])
        scan.scan(self.proj, self.state)
        self.assertEqual(len(self.usage()[0]["prompt"]), 300)

    def test_incremental_second_run_adds_only_new_lines(self):
        t0 = self.now - 100
        p = self.transcript([user(t0, "first prompt here"), tool(t0 + 1, "Skill", {"skill": "a"})])
        self.assertEqual(scan.scan(self.proj, self.state)["events"], 1)
        self.assertEqual(scan.scan(self.proj, self.state)["events"], 0)
        write_jsonl(p, [tool(t0 + 5, "Skill", {"skill": "b"})], "a")
        self.assertEqual(scan.scan(self.proj, self.state)["events"], 1)
        names = [e["name"] for e in self.usage()]
        self.assertEqual(names, ["a", "b"])
        self.assertEqual(self.usage()[1]["prompt"], "first prompt here")  # prompt carried across runs

    def test_partial_last_line_waits_for_newline(self):
        t0 = self.now - 100
        p = self.transcript([user(t0, "hello there friend")])
        with open(p, "a") as f:
            f.write(json.dumps(tool(t0 + 1, "Skill", {"skill": "a"}), separators=(",", ":"))[:30])
        scan.scan(self.proj, self.state)
        with open(p, "a") as f:
            f.write(json.dumps(tool(t0 + 1, "Skill", {"skill": "a"}), separators=(",", ":"))[30:] + "\n")
        self.assertEqual(scan.scan(self.proj, self.state)["events"], 1)

    def test_rebuild_and_days(self):
        old = self.now - 40 * 86400
        self.transcript([user(old, "old prompt"), tool(old + 1, "Skill", {"skill": "old"})], session="o")
        os.utime(f"{self.proj}/-Users-me-code-app/o.jsonl", (old, old))
        self.transcript([user(self.now - 9, "new prompt"), tool(self.now - 8, "Skill", {"skill": "new"})], session="n")
        scan.scan(self.proj, self.state, days=30)
        self.assertEqual([e["name"] for e in self.usage()], ["new"])
        scan.scan(self.proj, self.state, rebuild=True)
        self.assertEqual(sorted(e["name"] for e in self.usage()), ["new", "old"])

    def test_turns_numbered_and_events_carry_seq(self):
        t0 = self.now - 100
        self.transcript([user(t0, "one"), user(t0 + 5, "two two two"), tool(t0 + 6, "Skill", {"skill": "a"})])
        scan.scan(self.proj, self.state)
        turns = read_jsonl(self.state + "/turns.jsonl")
        self.assertEqual([x["seq"] for x in turns], [0, 1])
        self.assertEqual(self.usage()[0]["seq"], 1)

    FIXTURES = os.path.join(ROOT, "tests", "fixtures", "jdelegate-dry-run")  # copied from real `jdelegate --dry-run` runs

    def jd_run(self, harness, name):
        run = f"{self.d}/jd/2026-10-02T21-48-57-000Z-fix-the-login-bug-T3-{name}"
        shutil.copytree(os.path.join(self.FIXTURES, harness), run)
        return run

    def test_jdelegate_runs(self):
        self.jd_run("claude", "aaaaa")
        scan.scan(self.proj, self.state, jdelegate=self.d + "/jd")
        rows = [e for e in self.usage() if e["via"] == "jdelegate"]
        self.assertEqual({(e["kind"], e["name"]) for e in rows}, {("skill", "debugging"), ("agent", "planner")})
        self.assertEqual({e["prompt"] for e in rows}, {"fix the login bug"})
        before = len(self.usage())
        scan.scan(self.proj, self.state, jdelegate=self.d + "/jd")
        self.assertEqual(len(self.usage()), before)

    def test_jdelegate_non_claude_worker_prompt_is_in_brief_and_task_is_after_the_marker(self):
        self.jd_run("codex", "bbbbb")
        scan.scan(self.proj, self.state, jdelegate=self.d + "/jd")
        rows = [e for e in self.usage() if e["via"] == "jdelegate"]
        self.assertEqual({(e["kind"], e["name"]) for e in rows}, {("skill", "debugging"), ("agent", "planner")})
        self.assertEqual({e["prompt"] for e in rows}, {"fix the login bug"})

    def test_jdelegate_task_text_mentioning_skill_headings_is_not_a_use(self):
        run = self.jd_run("claude", "ccccc")
        os.remove(run + "/worker-prompt.md")
        open(run + "/brief.md", "w").write("explain this\n## Skill: not-used\n")
        scan.scan(self.proj, self.state, jdelegate=self.d + "/jd")
        self.assertFalse(os.path.exists(self.state + "/usage.jsonl"))  # no event at all

    def test_jdelegate_dir_env_matches_jdelegates_own_name(self):
        os.environ.pop("JDELEGATE_CACHE_DIR", None)
        os.environ["JDELEGATE_CACHE"] = self.d + "/jd"
        try:
            self.assertEqual(scan.jdelegate_dir(), self.d + "/jd")
        finally:
            del os.environ["JDELEGATE_CACHE"]
            os.environ["JDELEGATE_CACHE_DIR"] = self.d + "/jd-none"


def mk_skill(root, name, desc="Does a thing", link=None):
    os.makedirs(root, exist_ok=True)
    if link:
        os.symlink(link, f"{root}/{name}")
        return
    os.makedirs(f"{root}/{name}")
    open(f"{root}/{name}/SKILL.md", "w").write(f"---\nname: {name}\ndescription: {desc}\n---\nbody")


def mk_agent(root, name, link=None):
    os.makedirs(root, exist_ok=True)
    if link:
        os.symlink(link, f"{root}/{name}.md")
        return
    open(f"{root}/{name}.md", "w").write(f"---\nname: {name}\ndescription: agent {name}\n---\nbody")


def ev(now, days_ago, kind, name, prompt="p", project="proj"):
    return {"ts": int(now - days_ago * 86400), "session": "s", "project": project, "kind": kind, "name": name,
            "via": "skill-tool", "prompt": prompt}


class RegistryTest(Base):
    def build(self):
        return registry.build(self.state, self.d + "/claude", self.d + "/claude.json", now=self.now)

    def test_aggregation_windows_examples_and_location(self):
        home = self.d + "/claude"
        mk_skill(home + "/skills", "live-one")
        mk_skill(home + "/skills-parked", "parked-one")
        mk_skill(home + "/skills", "never-used")
        mk_agent(home + "/agents-parked", "planner")
        json.dump({"mcpServers": {"github": {}}, "projects": {"/x": {"mcpServers": {"slack": {}}}}},
                  open(self.d + "/claude.json", "w"))
        os.makedirs(self.state)
        evs = [ev(self.now, 1, "skill", "live-one", "alpha prompt", "A"),
               ev(self.now, 2, "skill", "live-one", "alpha prompt", "A"),       # duplicate example
               ev(self.now, 3, "skill", "live-one", "beta prompt", "B"),
               ev(self.now, 10, "skill", "live-one", "gamma prompt", "A"),
               ev(self.now, 20, "skill", "live-one", "delta prompt", "C"),
               ev(self.now, 25, "skill", "live-one", "eps prompt", "D"),
               ev(self.now, 45, "skill", "live-one", "ancient", "A"),
               ev(self.now, 5, "skill", "parked-one"),
               ev(self.now, 1, "agent", "planner"),
               ev(self.now, 1, "mcp", "github")]
        write_jsonl(self.state + "/usage.jsonl", evs)
        reg = self.build()
        it = reg["items"]
        lo = it["skill:live-one"]
        self.assertEqual((lo["uses_7d"], lo["uses_14d"], lo["uses_30d"]), (3, 4, 6))
        self.assertEqual(lo["location"], "live")
        self.assertEqual(lo["projects"][0], "A")
        self.assertEqual(len(lo["projects"]), 3)
        self.assertEqual(lo["examples"], ["alpha prompt", "beta prompt", "gamma prompt"])
        self.assertTrue(lo["last_used"].startswith(iso(self.now - 86400)[:10]))
        self.assertEqual(it["skill:parked-one"]["location"], "parked")
        self.assertEqual(it["skill:never-used"]["uses_30d"], 0)
        self.assertIsNone(it["skill:never-used"]["last_used"])
        self.assertEqual(it["agent:planner"]["location"], "parked")
        self.assertEqual(it["agent:planner"]["uses_7d"], 1)
        self.assertEqual(it["mcp:github"]["uses_30d"], 1)
        self.assertIn("mcp:slack", it)
        self.assertEqual(it["skill:live-one"]["description"], "Does a thing")

    def test_uses_14d_counts_every_via_including_sub_agent_events(self):
        mk_skill(self.d + "/claude/skills-parked", "p")
        os.makedirs(self.state)
        write_jsonl(self.state + "/usage.jsonl", [
            dict(ev(self.now, 1, "skill", "p"), via="parked-read"),
            dict(ev(self.now, 1, "skill", "p"), via="jdelegate"),
            dict(ev(self.now, 1, "skill", "p"), via="skill-tool", sub=True)])
        self.assertEqual(self.build()["items"]["skill:p"]["uses_14d"], 3)

    def test_precision_from_outcomes(self):
        home = self.d + "/claude"
        mk_skill(home + "/skills-parked", "alpha")
        os.makedirs(self.state)
        write_jsonl(self.state + "/usage.jsonl", [])
        os.makedirs(self.d + "/jev")
        rows = []
        for i, outc in enumerate(["alpha", "alpha", "other", "none"]):
            rows.append({"kind_of_record": "decision", "id": f"d{i}", "ts": 1, "tag": "skill-suggest", "kind": "choice",
                         "value": "alpha", "question": {"type": "choice", "instructions": "Which of these skills or agents does X"}})
            rows.append({"kind_of_record": "outcome", "id": f"d{i}", "ts": 2, "outcome": outc})
        rows.append({"kind_of_record": "decision", "id": "w", "ts": 1, "tag": "skill-suggest", "kind": "choice",
                     "value": "alpha", "question": {"type": "choice", "instructions": "Which installed agent skill"}})
        rows.append({"kind_of_record": "outcome", "id": "w", "ts": 2, "outcome": "alpha"})  # wide stage: not counted
        write_jsonl(self.d + "/jev/decisions.jsonl", rows)
        a = self.build()["items"]["skill:alpha"]
        self.assertEqual((a["suggested_n"], a["followed_n"]), (4, 2))
        self.assertAlmostEqual(a["precision"], 0.5)

    def test_report_sorted_by_uses(self):
        reg = {"items": {"skill:a": {"kind": "skill", "name": "a", "location": "live", "uses_30d": 1, "last_used": "2026-09-01T00:00:00Z", "precision": None},
                         "skill:b": {"kind": "skill", "name": "b", "location": "parked", "uses_30d": 9, "last_used": "2026-09-30T00:00:00Z", "precision": 0.5}}}
        out = registry.report(reg).splitlines()
        self.assertIn("kind", out[0])
        self.assertIn("precision", out[0])
        self.assertTrue(out[1].split()[1] == "b")


CANDIDATES = ["deploy", "debugging", "agent:planner"]


def decision(did, ts, request, value, instr="Which of these skills or agents does X", state_hash="h1", kind="choice",
             candidates=CANDIDATES, confidence=None):
    return {"kind_of_record": "decision", "id": did, "ts": ts, "tag": "skill-suggest", "state_hash": state_hash,
            "state_preview": json.dumps({"recent_context": "", "request": request}, sort_keys=True),
            "question": {"type": kind, "instructions": instr, "criteria": {c: "d" for c in candidates}},
            "kind": kind, "value": value, "confidence": confidence}


def fits(did, ts, value, state_hash="h1", skill="deploy"):
    """The rerank 'fits' score of one candidate."""
    return {"kind_of_record": "decision", "id": did, "ts": ts, "tag": "skill-suggest", "state_hash": state_hash,
            "state_preview": "", "question": {"type": "noul", "instructions": f"The skill `{skill}` does the specific thing"},
            "kind": "noul", "value": value}


WIDE = "Which installed agent skill is most"
GATE_Q = {"acts_on_user_system": "`request` asks the agent to act on the user's files",
          "would_follow_documented_procedure": "Doing `request` well needs a specific documented procedure",
          "prose_suffices": "A plain written answer alone fully satisfies `request`"}


def gate(ts, acts, procedure, prose, state_hash="h1"):
    """The three wide-stage gate answers."""
    return [{"kind_of_record": "decision", "id": f"g-{k}-{ts}", "ts": ts, "tag": "skill-suggest", "state_hash": state_hash,
             "state_preview": "", "question": {"type": "noul", "instructions": q}, "kind": "noul", "value": v}
            for (k, q), v in zip(GATE_Q.items(), (acts, procedure, prose))]


class OutcomesTest(Base):
    PROMPT = "please set up the deployment pipeline for this repo"

    def setup_session(self, used, extra_turns=3, session="s1", prompt=None):
        t0 = int(self.now - 1000)
        rows = [user(t0, prompt or self.PROMPT, session)]
        for i, (kind, name) in enumerate(used):
            if kind == "skill":
                rows.append(tool(t0 + 1 + i, "Skill", {"skill": name}, session))
            else:
                rows.append(tool(t0 + 1 + i, "Agent", {"subagent_type": name}, session))
        for i in range(extra_turns):
            rows.append(user(t0 + 60 + i * 30, f"follow up number {i} with text", session))
        self.transcript(rows, session=session)
        scan.scan(self.proj, self.state)
        return t0

    def run_outcomes(self, decisions, **kw):
        write_jsonl(self.d + "/jev/decisions.jsonl", decisions)
        return outcomes.run(self.state, **kw)

    def recorded(self):
        return {r["id"]: r["outcome"] for r in read_jsonl(self.d + "/jev/decisions.jsonl")
                if r.get("kind_of_record") == "outcome"}

    def test_followed(self):
        t0 = self.setup_session([("skill", "deploy")])
        c = self.run_outcomes([decision("d1", t0 + 2, self.PROMPT, "deploy"), fits("f1", t0 + 2, 0.9)])
        self.assertEqual(self.recorded(), {"d1": "deploy"})
        self.assertEqual(c["followed"], 1)

    def test_other_used(self):
        t0 = self.setup_session([("skill", "debugging")])
        c = self.run_outcomes([decision("d1", t0 + 2, self.PROMPT, "deploy"), fits("f1", t0 + 2, 0.9)])
        self.assertEqual(self.recorded(), {"d1": "debugging"})
        self.assertEqual(c["other"], 1)

    def test_agent_used_is_prefixed(self):
        t0 = self.setup_session([("agent", "planner")])
        self.run_outcomes([decision("d1", t0 + 2, self.PROMPT, "agent:planner"), fits("f1", t0 + 2, 0.9, skill="agent:planner")])
        self.assertEqual(self.recorded(), {"d1": "agent:planner"})

    def test_none_only_when_session_continued(self):
        t0 = self.setup_session([], extra_turns=3)
        c = self.run_outcomes([decision("d1", t0 + 2, self.PROMPT, "deploy", candidates=["deploy", "none"]), fits("f1", t0 + 2, 0.9)])
        self.assertEqual(self.recorded(), {"d1": "none"})
        self.assertEqual(c["none"], 1)

    def test_session_that_stopped_is_skipped(self):
        t0 = self.setup_session([], extra_turns=0)
        c = self.run_outcomes([decision("d1", t0 + 2, self.PROMPT, "deploy"), fits("f1", t0 + 2, 0.9)])
        self.assertEqual(self.recorded(), {})
        self.assertEqual(c["skipped_no_evidence"], 1)

    def test_nothing_suggested_but_used_labels_wide_decision(self):
        t0 = self.setup_session([("skill", "debugging")])
        c = self.run_outcomes([decision("w1", t0 + 2, self.PROMPT, "deploy", instr=WIDE), *gate(t0 + 2, 0.9, 0.9, 0.1)])
        self.assertEqual(self.recorded(), {"w1": "debugging"})
        self.assertEqual(c["other"], 1)

    def test_shown_uses_the_live_thresholds_of_jev_skill_suggest(self):
        self.assertEqual((sug.GATE_THRESHOLD, sug.FITS_THRESHOLD, sug.WIDE_BYPASS_CONFIDENCE), (0.6, 0.8, 0.99))
        t = outcomes.thresholds()
        self.assertEqual((t.GATE_THRESHOLD, t.FITS_THRESHOLD, t.WIDE_BYPASS_CONFIDENCE), (0.6, 0.8, 0.99))
        self.assertFalse(hasattr(outcomes, "FITS_THRESHOLD"))  # no private copy

    def test_rerank_between_old_and_live_fits_threshold_is_not_shown(self):
        t0 = self.setup_session([("skill", "deploy")])
        c = self.run_outcomes([decision("d1", t0 + 2, self.PROMPT, "deploy"), fits("f1", t0 + 2, 0.5)])
        self.assertEqual(self.recorded(), {})
        self.assertEqual(c["skipped_not_shown"], 1)

    def test_rerank_needs_the_winners_own_fits_score(self):
        t0 = self.setup_session([("skill", "deploy")])
        c = self.run_outcomes([decision("d1", t0 + 2, self.PROMPT, "deploy"), fits("f1", t0 + 2, 0.1, skill="deploy"),
                               fits("f2", t0 + 2, 0.95, skill="debugging")])
        self.assertEqual(self.recorded(), {})
        self.assertEqual(c["skipped_not_shown"], 1)

    def test_wide_below_gate_is_not_shown_unless_bypass_confidence(self):
        t0 = self.setup_session([("skill", "deploy")])
        low = gate(t0 + 2, 0.5, 0.5, 0.5)  # (0.5 + 0.5 + 0.5) / 3 = 0.5 < 0.6
        c = self.run_outcomes([decision("w1", t0 + 2, self.PROMPT, "deploy", instr=WIDE), *low])
        self.assertEqual((self.recorded(), c["skipped_not_shown"]), ({}, 1))
        self.run_outcomes([decision("w1", t0 + 2, self.PROMPT, "deploy", instr=WIDE, confidence=0.995), *low])
        self.assertEqual(self.recorded(), {"w1": "deploy"})

    def test_wide_without_gate_answers_is_not_shown(self):
        t0 = self.setup_session([("skill", "deploy")])
        c = self.run_outcomes([decision("w1", t0 + 2, self.PROMPT, "deploy", instr=WIDE)])
        self.assertEqual((self.recorded(), c["skipped_not_shown"]), ({}, 1))

    def test_outcome_must_be_one_of_the_choice_keys(self):
        t0 = self.setup_session([], extra_turns=3)  # nothing used -> would be "none", which is not a key
        c = self.run_outcomes([decision("d1", t0 + 2, self.PROMPT, "deploy"), fits("f1", t0 + 2, 0.9)])
        self.assertEqual(self.recorded(), {})
        self.assertEqual(c["skipped_bad_label"], 1)

    def test_skill_outside_the_candidates_is_not_a_label(self):
        t0 = self.setup_session([("skill", "outsider")])
        c = self.run_outcomes([decision("d1", t0 + 2, self.PROMPT, "deploy"), fits("f1", t0 + 2, 0.9)])
        self.assertEqual((self.recorded(), c["skipped_bad_label"]), ({}, 1))

    def test_none_is_written_when_none_is_a_choice_key(self):
        t0 = self.setup_session([], extra_turns=3)
        self.run_outcomes([decision("d1", t0 + 2, self.PROMPT, "deploy", candidates=["deploy", "none"]), fits("f1", t0 + 2, 0.9)])
        self.assertEqual(self.recorded(), {"d1": "none"})

    def test_rerank_not_shown_is_skipped(self):
        t0 = self.setup_session([("skill", "deploy")])
        self.run_outcomes([decision("d1", t0 + 2, self.PROMPT, "deploy"), fits("f1", t0 + 2, 0.1)])
        self.assertEqual(self.recorded(), {})

    def test_ambiguous_two_sessions_skipped(self):
        t0 = self.setup_session([("skill", "deploy")], session="s1")
        self.setup_session([("skill", "deploy")], session="s2")
        c = self.run_outcomes([decision("d1", t0 + 2, self.PROMPT, "deploy"), fits("f1", t0 + 2, 0.9)])
        self.assertEqual(self.recorded(), {})
        self.assertEqual(c["skipped_ambiguous"], 1)

    def test_outside_time_window_unmatched(self):
        t0 = self.setup_session([("skill", "deploy")])
        c = self.run_outcomes([decision("d1", t0 + 5000, self.PROMPT, "deploy"), fits("f1", t0 + 5000, 0.9)])
        self.assertEqual(c["skipped_unmatched"], 1)

    def test_idempotent_and_dry_run(self):
        t0 = self.setup_session([("skill", "deploy")])
        decs = [decision("d1", t0 + 2, self.PROMPT, "deploy"), fits("f1", t0 + 2, 0.9)]
        c = self.run_outcomes(decs, dry_run=True)
        self.assertEqual(c["followed"], 1)
        self.assertEqual(self.recorded(), {})
        outcomes.run(self.state)
        outcomes.run(self.state)
        n = len([r for r in read_jsonl(self.d + "/jev/decisions.jsonl") if r.get("kind_of_record") == "outcome"])
        self.assertEqual(n, 1)
        self.assertEqual(outcomes.run(self.state)["already"], 1)

    def test_only_turns_window_counts(self):
        t0 = int(self.now - 1000)
        rows = [user(t0, self.PROMPT)] + [user(t0 + 10 + i, f"filler turn number {i} text") for i in range(8)]
        rows.append(tool(t0 + 50, "Skill", {"skill": "late"}))
        self.transcript(rows)
        scan.scan(self.proj, self.state)
        self.run_outcomes([decision("d1", t0 + 2, self.PROMPT, "deploy", candidates=["deploy", "none"]), fits("f1", t0 + 2, 0.9)], turns=6)
        self.assertEqual(self.recorded(), {"d1": "none"})


class RerankStateTest(unittest.TestCase):
    ROSTER = {n: {"description": f"{n} desc", "excerpt": "ex"} for n in ("a", "b", "c")}

    def fake(self, calls):
        def ask_many(state, questions, tag, timeout):
            calls.append((state, questions))
            if "skill" in questions:
                return ({"skill": {"choice": "a", "probabilities": {"a": 0.5, "b": 0.3, "c": 0.2}, "confidence": 0.95},
                         "acts_on_user_system": {"noul": 0.9}, "would_follow_documented_procedure": {"noul": 0.9},
                         "prose_suffices": {"noul": 0.1}}, None, None)
            return ({"winner": {"choice": "a"}, "fits_0": {"noul": 0.9}, "fits_1": {"noul": 0.1}, "fits_2": {"noul": 0.1}}, None, None)
        return ask_many

    def test_identical_without_registry(self):
        c1, c2 = [], []
        r1 = sug.suggest("a long enough prompt here", self.ROSTER, self.fake(c1))
        r2 = sug.suggest("a long enough prompt here", self.ROSTER, self.fake(c2), usage={})
        self.assertEqual(r1, r2)
        self.assertEqual(c1, c2)
        self.assertEqual(c1[1][0], {"request": "a long enough prompt here", "recent_context": ""})

    def test_rerank_state_includes_usage_fields(self):
        usage = {"a": {"uses_30d": 4, "last_used": "2026-09-30T00:00:00Z", "precision": 0.75,
                       "examples": ["p1", "p2"], "location": "parked"}}
        calls = []
        sug.suggest("a long enough prompt here", self.ROSTER, self.fake(calls), usage=usage)
        self.assertEqual(calls[0][0], {"request": "a long enough prompt here", "recent_context": ""})  # wide unchanged
        u = calls[1][0]["usage"]["a"]
        self.assertEqual((u["uses_30d"], u["last_used"], u["precision"]), (4, "2026-09-30T00:00:00Z", 0.75))
        self.assertEqual(u["past prompts that used it"], ["p1", "p2"])
        self.assertNotIn("b", calls[1][0]["usage"])

    def test_stale_live_gets_no_boost(self):
        usage = {"b": {"uses_30d": 0, "location": "live", "last_used": None, "examples": []},
                 "c": {"uses_30d": 10, "location": "live", "last_used": "x", "examples": []}}
        self.assertEqual(sug.boost("b", usage), 1.0)
        self.assertGreater(sug.boost("c", usage), 1.0)
        self.assertEqual(sug.boost("zzz", usage), 1.0)

    def test_load_usage_tolerates_missing_and_corrupt(self):
        with tempfile.TemporaryDirectory() as d:
            os.environ["DEVSTACK_STATE"] = d
            try:
                self.assertEqual(sug.load_usage(), {})
                open(d + "/capabilities.json", "w").write("{not json")
                self.assertEqual(sug.load_usage(), {})
                json.dump({"items": {"skill:a": {"name": "a", "kind": "skill", "uses_30d": 2},
                                     "agent:p": {"name": "p", "kind": "agent", "uses_30d": 1}}},
                          open(d + "/capabilities.json", "w"))
                u = sug.load_usage()
                self.assertEqual(u["a"]["uses_30d"], 2)
                self.assertEqual(u["agent:p"]["uses_30d"], 1)
            finally:
                del os.environ["DEVSTACK_STATE"]


def park(home, *args, policy=None):
    env = {**os.environ, "HOME": home, "CLAUDE_HOME": home + "/.claude"}
    if policy:
        env["CAPABILITY_POLICY"] = policy
    return subprocess.run(["bash", PARK, *args], env=env, capture_output=True, text=True)


class AutoParkTest(Base):
    def setUp(self):
        super().setUp()
        self.home = self.d + "/home"
        self.src = self.d + "/src"
        self.live = self.home + "/.claude/skills"
        self.parked = self.home + "/.claude/skills-parked"
        for n in ("pinned", "busy", "idle", "wake", "pinned-parked"):
            mk_skill(self.src, n)
        mk_skill(self.live, "pinned", link=self.src + "/pinned")
        mk_skill(self.live, "busy", link=self.src + "/busy")
        mk_skill(self.live, "idle", link=self.src + "/idle")
        mk_skill(self.live, "realdir")  # real directory: never touched
        mk_skill(self.parked, "wake", link=self.src + "/wake")
        mk_skill(self.parked, "pinned-parked", link=self.src + "/pinned-parked")
        mk_agent(self.home + "/.claude/agents", "planner", link=self.src + "/planner.md")
        mk_agent(self.home + "/.claude/agents", "debugger", link=self.src + "/debugger.md")
        self.policy = self.d + "/policy.json"
        json.dump({"pin_skills": ["pinned", "pinned-parked"], "pin_agents": ["debugger"],
                   "keep_if_uses_14d_at_least": 3}, open(self.policy, "w"))
        sd = self.home + "/.local/state/dev-stack"
        os.makedirs(sd)
        item = lambda kind, name, loc, u: {"kind": kind, "name": name, "location": loc, "uses_14d": u, "uses_30d": u}
        items = [item("skill", "pinned", "live", 0), item("skill", "busy", "live", 5), item("skill", "idle", "live", 2),
                 item("skill", "realdir", "live", 0), item("skill", "wake", "parked", 3),
                 item("skill", "pinned-parked", "parked", 0), item("agent", "planner", "live", 0),
                 item("agent", "debugger", "live", 0), item("skill", "pl:x", "live", 0)]
        json.dump({"items": {f"{i['kind']}:{i['name']}": i for i in items}}, open(sd + "/capabilities.json", "w"))
        self.sd = sd
        self.set_usage(1, 1)

    def set_usage(self, events, files):
        """usage.jsonl with `events` rows and a scan-state that covered `files` files."""
        with open(self.sd + "/usage.jsonl", "w") as f:
            f.write('{"kind":"skill","name":"busy"}\n' * events)
        json.dump({"files": {f"/t/{i}.jsonl": {"off": 1} for i in range(files)}}, open(self.sd + "/scan-state.json", "w"))

    def test_refuses_plan_when_usage_missing_or_empty_or_scan_covered_nothing(self):
        for setup in (lambda: os.remove(self.sd + "/usage.jsonl"), lambda: self.set_usage(0, 3), lambda: self.set_usage(5, 0)):
            self.set_usage(1, 1)
            setup()
            for args in (("auto",), ("auto", "--apply")):
                r = park(self.home, *args, policy=self.policy)
                self.assertNotEqual(r.returncode, 0, r.stdout)
                self.assertNotIn("would move", r.stdout)
                self.assertTrue(os.path.islink(self.live + "/idle"))

    def test_apply_refuses_a_plan_that_parks_more_than_eight_unless_forced(self):
        for i in range(10):
            mk_skill(self.src, f"extra{i}")
            mk_skill(self.live, f"extra{i}", link=f"{self.src}/extra{i}")
        reg = json.load(open(self.sd + "/capabilities.json"))
        for i in range(10):
            reg["items"][f"skill:extra{i}"] = {"kind": "skill", "name": f"extra{i}", "location": "live", "uses_14d": 0, "uses_30d": 0}
        json.dump(reg, open(self.sd + "/capabilities.json", "w"))
        r = park(self.home, "auto", policy=self.policy)  # a dry run still shows the plan
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("would move extra9 -> ", r.stdout)
        r = park(self.home, "auto", "--apply", policy=self.policy)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("--force", r.stdout + r.stderr)
        self.assertTrue(os.path.islink(self.live + "/extra0") and os.path.islink(self.live + "/idle"))
        r = park(self.home, "auto", "--apply", "--force", policy=self.policy)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(os.path.lexists(self.live + "/extra0"))
        self.assertTrue(os.path.lexists(self.parked + "/extra0"))

    def test_dry_run_plan(self):
        r = park(self.home, "auto", policy=self.policy)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("would move idle -> ", r.stdout)
        self.assertIn("would move wake -> ", r.stdout)
        self.assertIn("would move pinned-parked -> ", r.stdout)
        self.assertIn("would move planner.md -> ", r.stdout)
        self.assertNotIn("busy", r.stdout)
        self.assertNotIn("would move pinned ", r.stdout)
        self.assertNotIn("debugger", r.stdout)
        self.assertNotIn("pl:x", r.stdout)
        self.assertIn("realdir", r.stdout)
        self.assertIn("real directory", r.stdout)
        self.assertTrue(os.path.islink(self.live + "/idle"))  # nothing moved

    def test_shipped_policy_pins_the_mandated_pipeline(self):
        with open(os.path.join(ROOT, "config", "capability-policy.json")) as f:
            policy = json.load(f)
        need = ["brainstorming", "writing-plans", "kb-compile", "kb-ingest", "kb-lint", "requesting-code-review",
                "receiving-code-review", "kb-query", "kb-spec", "kb-dev", "test-driven-development",
                "verification-before-completion", "systematic-debugging", "karpathy-guidelines", "jev", "lean-ctx"]
        self.assertEqual([n for n in need if n not in policy["pin_skills"]], [])
        items = {f"skill:{n}": {"kind": "skill", "name": n, "location": "live", "uses_14d": 0} for n in need}
        plan = registry.park_plan({"items": items}, policy, self.home + "/.claude")
        self.assertEqual(plan, [])

    def test_apply_moves_and_leaves_real_dirs(self):
        r = park(self.home, "auto", "--apply", policy=self.policy)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(os.path.lexists(self.parked + "/idle"))
        self.assertFalse(os.path.lexists(self.live + "/idle"))
        self.assertTrue(os.path.lexists(self.live + "/wake"))
        self.assertTrue(os.path.lexists(self.live + "/pinned-parked"))
        self.assertTrue(os.path.isdir(self.live + "/realdir") and not os.path.islink(self.live + "/realdir"))
        self.assertTrue(os.path.lexists(self.live + "/busy"))
        self.assertTrue(os.path.lexists(self.home + "/.claude/agents-parked/planner.md"))
        self.assertTrue(os.path.lexists(self.home + "/.claude/agents/debugger.md"))

    def test_refuses_without_registry(self):
        os.remove(self.home + "/.local/state/dev-stack/capabilities.json")
        r = park(self.home, "auto", "--apply", policy=self.policy)
        self.assertNotEqual(r.returncode, 0)
        self.assertTrue(os.path.lexists(self.live + "/idle"))


class ParkAgentMultiNameTest(Base):
    def setUp(self):
        super().setUp()
        self.home = self.d + "/home"
        self.alive = self.home + "/.claude/agents"
        self.aparked = self.home + "/.claude/agents-parked"
        for n in ("a", "b", "c"):
            mk_agent(self.alive, n)

    def test_park_agent_handles_each_name_separately(self):
        r = park(self.home, "park-agent", "a", "b", "ghost", "c")
        self.assertEqual(r.returncode, 0, r.stderr)
        for n in ("a", "b", "c"):
            self.assertTrue(os.path.exists(f"{self.aparked}/{n}.md"), r.stdout)
            self.assertFalse(os.path.exists(f"{self.alive}/{n}.md"))
        self.assertIn("missing " + self.alive + "/ghost.md", r.stdout)
        self.assertNotIn("a b", r.stdout)

    def test_unpark_agent_multi_and_keep_agents(self):
        park(self.home, "park-agent", "a", "b", "c")
        r = park(self.home, "unpark-agent", "a", "c")
        self.assertTrue(os.path.exists(self.alive + "/a.md") and os.path.exists(self.alive + "/c.md"), r.stdout)
        self.assertFalse(os.path.exists(self.alive + "/b.md"))
        r = park(self.home, "keep-agents", "a", "b")
        self.assertTrue(os.path.exists(self.alive + "/a.md"))
        self.assertTrue(os.path.exists(self.aparked + "/c.md"))

    def test_park_unpark_skills_multi(self):
        live, parked = self.home + "/.claude/skills", self.home + "/.claude/skills-parked"
        for n in ("x", "y", "z"):
            mk_skill(live, n)
        r = park(self.home, "park", "x", "y")
        self.assertTrue(os.path.exists(parked + "/x") and os.path.exists(parked + "/y"), r.stdout)
        r = park(self.home, "unpark", "x", "y")
        self.assertTrue(os.path.exists(live + "/x") and os.path.exists(live + "/y"), r.stdout)
        r = park(self.home, "keep", "z")
        self.assertTrue(os.path.exists(parked + "/x") and os.path.exists(live + "/z"))


if __name__ == "__main__":
    unittest.main()
