"""Tests for config/tiers.proposed.json and config/tiers.proposed.diff (P6.20).

The proposal is a copy of ~/.config/jev-router/tiers.json with the P6 policy changes (pm-models.md D0, D2, Q4, Q7).
It is never written over the live file: the owner applies it (P6.OG1). Nothing here calls a model or touches the live file.

Readers exercised: control/reviewpick.py (review-pick --check-tiers) and control/model_health.py of software-factory
(env SF_ROOT, default the p6-integ worktree; run with SF_PY), the jdelegate loader (node, JEV_ROUTER_CONFIG, a failing Jev),
and a JSON-parse plus key-presence check for the pi extension and tokyo-zen-cli. software-factory's router/route.py and
router/auto.py do not read tiers.json; they are only imported to prove the proposal does not break them.
"""
import datetime
import difflib
import json
import os
import re
import subprocess
import tempfile

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PROPOSED = os.path.join(ROOT, "config", "tiers.proposed.json")
DIFF = os.path.join(ROOT, "config", "tiers.proposed.diff")
JDELEGATE = os.path.join(ROOT, "bin", "jdelegate")
SF_ROOT = os.environ.get("SF_ROOT", "/root/projects/software-factory-wt/p6-integ")
SF_PY = os.environ.get("SF_PY", "/root/projects/software-factory-wt/main/.venv/bin/python")
PI_EXT = os.path.expanduser("~/.pi/agent/extensions/model-router/index.ts")
TOKYO_ZEN = "/usr/local/bin/tokyo-zen-cli"

# keys carrying history, notes or the model-intel blocklist: not routing data
PROSE_KEYS = ("_comment", "_notes", "_blocked")
# providers the owner pays for by subscription (pm-models.md D0)
SUBSCRIPTION = {"cliproxy", "xai", "opencode-go", "oc-sdk-go", "agy", "gemini"}


def load():
    with open(PROPOSED) as fh:
        return json.load(fh)


def chains(data):
    """(path, list) for every model chain: tiers.T*, kinds.<kind>.T*, orchestrator."""
    out = [(f"tiers.{t}", c) for t, c in data["tiers"].items()]
    out += [(f"kinds.{k}.{t}", c) for k, v in data["kinds"].items() for t, c in v.items()]
    out.append(("orchestrator", data["orchestrator"]))
    return out


def strings(node, skip=PROSE_KEYS):
    """Every key and string value outside the prose keys."""
    if isinstance(node, dict):
        for k, v in node.items():
            if k in skip:
                continue
            yield k
            yield from strings(v, skip)
    elif isinstance(node, list):
        for v in node:
            yield from strings(v, skip)
    elif isinstance(node, str):
        yield node


def provider(ref):
    return ref.split("/", 1)[0]


def test_no_openrouter_anywhere():
    with open(PROPOSED) as fh:
        raw = fh.read()
    assert "openrouter/" not in raw
    data = json.loads(raw)
    assert not [s for s in strings(data) if s.lower().startswith("openrouter/")]
    for path, chain in chains(data):
        assert not [m for m in chain if provider(m) == "openrouter"], path


def test_no_openai_anywhere():
    data = load()
    bad = [s for s in strings(data) if re.search(r"openai|codex|gpt", s, re.I)]
    assert not bad, bad


def test_language_chain_claude_only():
    language = load()["kinds"]["language"]
    assert language, "kinds.language is missing"
    for tier, chain in language.items():
        assert chain, tier
        for ref in chain:
            assert provider(ref) == "cliproxy" and "claude" in ref, f"{tier}: {ref}"


def test_every_chain_has_a_subscription_entry():
    data = load()
    for path, chain in chains(data):
        assert chain, f"{path} is empty"
        assert any(provider(m) in SUBSCRIPTION for m in chain), f"{path}: only {chain}"
        # Q7: commandcode is the last class in a chain, never ahead of a subscription entry
        seen_cc = False
        for m in chain:
            if provider(m) == "commandcode":
                seen_cc = True
            else:
                assert not seen_cc, f"{path}: {m} after a commandcode entry"


def test_native_grok_before_opencode_grok():
    data = load()
    found = 0
    for path, chain in chains(data):
        if "opencode-go/grok-4.7" in chain:
            found += 1
            assert "xai/grok-4.7" in chain, path
            assert chain.index("xai/grok-4.7") < chain.index("opencode-go/grok-4.7"), path
    assert found


def test_new_kinds_and_pins():
    data = load()
    research, doer_open = data["kinds"]["research"], data["kinds"]["doer_open"]
    assert research["T1"][:2] == ["gemini/gemini-3.8-flash", "opencode-go/deepseek-v4.1-flash"]
    assert research["T2"][0] == "cliproxy/claude-haiku-5-5"
    assert research["T4"][0] == "agy/gemini-4-argon-high"
    assert doer_open and all(provider(m) != "cliproxy" for c in doer_open.values() for m in c)
    for kind in ("research", "doer_open"):
        assert data["kind_harness"][kind] == "pi"
        assert f"kinds.{kind}" in data["_pinned"]
    # every chain this proposal edits stays out of model-intel auto-apply
    for pin in ("kinds.vision", "kinds.language", "kinds.review", "kinds.test", "tiers.T2", "tiers.T3", "tiers.T4"):
        assert pin in data["_pinned"], pin


def _jdelegate_dry_run():
    with tempfile.TemporaryDirectory() as t:
        repo = os.path.join(t, "repo")
        os.mkdir(repo)
        subprocess.run(["git", "init", "-q", repo], check=True)
        jev = os.path.join(t, "jev")  # a failing Jev: jdelegate takes its safe default route from the chains
        with open(jev, "w") as fh:
            fh.write("#!/bin/sh\nexit 1\n")
        os.chmod(jev, 0o755)
        env = {**os.environ, "JEV_ROUTER_CONFIG": PROPOSED, "JDELEGATE_JEV": jev, "JDELEGATE_CACHE": os.path.join(t, "c"),
               "JDELEGATE_SELECT_CACHE": "0", "JDELEGATE_AUTO_MCP": "0", "JDELEGATE_AUTO_SKILL": "0", "WORLD_TRACK": "0",
               "FACTORY_BIN": "/bin/true", "JEV_QUOTA_FILE": os.path.join(t, "no-quota.json"),
               "JDELEGATE_QUOTA_SNAPSHOT": "/bin/true"}
        return subprocess.run(["node", JDELEGATE, "--dry-run", "--no-auto-role", "--cwd", repo, "say hi"],
                              capture_output=True, text=True, env=env, timeout=90)


def _jdelegate_pick(kind, tier, used):
    """(harness, ref) jdelegate picks for a brief Jev routes to kind/tier, with cliproxy and opencode-go at `used` of their quota."""
    with tempfile.TemporaryDirectory() as t:
        repo = os.path.join(t, "repo")
        os.mkdir(repo)
        subprocess.run(["git", "init", "-q", repo], check=True)
        answers = {"tier": {"choice": tier, "confidence": 0.9}, "kind": {"choice": kind, "confidence": 0.9},
                   "role": {"choice": "doer", "confidence": 0.9}}
        jev = os.path.join(t, "jev")  # a fake Jev: the route answer is fixed, nothing else is asked
        with open(jev, "w") as fh:
            fh.write("#!/bin/sh\ncat <<'EOF'\n" + json.dumps({"answers": answers}) + "\nEOF\n")
        os.chmod(jev, 0o755)
        quota = os.path.join(t, "quota.json")
        with open(quota, "w") as fh:
            json.dump({"at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                       "providers": {p: {"five_hour": used, "source": "api"} for p in ("cliproxy", "opencode-go")}}, fh)
        env = {**os.environ, "JEV_ROUTER_CONFIG": PROPOSED, "JDELEGATE_JEV": jev, "JDELEGATE_CACHE": os.path.join(t, "c"),
               "JDELEGATE_SELECT_CACHE": "0", "JDELEGATE_AUTO_MCP": "0", "JDELEGATE_AUTO_SKILL": "0", "WORLD_TRACK": "0",
               "FACTORY_BIN": "/bin/true", "JEV_QUOTA_FILE": quota, "JDELEGATE_QUOTA_SNAPSHOT": "/bin/true"}
        r = subprocess.run(["node", JDELEGATE, "--print", "--no-auto-role", "--cwd", repo, "say hi"],
                           capture_output=True, text=True, env=env, timeout=90)
    assert r.returncode == 0, r.stdout + r.stderr[-800:]
    m = re.search(r"→ (\w+) · (\S+) ·", r.stdout)
    assert m, r.stdout
    return m.group(1), m.group(2)


@pytest.mark.parametrize("used", [0.75, 0.95], ids=["warm", "hot"])
@pytest.mark.parametrize("kind,tier", [("code", "T2"), ("code", "T3"), ("language", "T2"), ("language", "T3")])
def test_hot_quota_never_picks_unrunnable_pi_ref(kind, tier, used):
    """jdelegate maps xai/ and gemini/ to the pi harness, which cannot run them (and would bill pay-per-token xAI)."""
    harness, ref = _jdelegate_pick(kind, tier, used)
    assert not (harness == "pi" and provider(ref) in ("xai", "gemini")), f"{kind} {tier} at {used}: {harness} {ref}"


@pytest.mark.parametrize("used", [0.75, 0.95], ids=["warm", "hot"])
def test_hot_quota_language_stays_on_claude(used):
    """jdelegate appends tiers.* after kinds.language and ignores quota_policy.exempt, so a hot cliproxy sends Arabic elsewhere."""
    for tier in ("T2", "T3"):
        _, ref = _jdelegate_pick("language", tier, used)
        assert provider(ref) == "cliproxy" and "claude" in ref, f"language {tier} at {used}: {ref}"


def test_language_exempt_from_quota_demotion():
    assert load()["quota_policy"]["exempt"]["language"] == ["cliproxy"]


def test_xai_gemini_rank_behind_hot_buckets():
    # quota ranking buckets: warm 2, hot 3; a provider with no quota data takes its provider_priority as bucket
    prio = load()["provider_priority"]
    assert prio["xai"] >= 4 and prio["gemini"] >= 4


def _sf(code):
    env = {**os.environ, "FACTORY_TIERS": PROPOSED, "PYTHONPATH": SF_ROOT}
    return subprocess.run([SF_PY, "-c", code], capture_output=True, text=True, env=env, cwd=SF_ROOT, timeout=90)


def test_all_readers_load_proposed_file():
    data = load()
    # pi extension and tokyo-zen-cli: JSON-parse (above) plus the keys the pi extension reads from CONFIG
    for key in ("tiers", "kinds", "kind_harness", "thinking", "orchestrator", "provider_priority", "budgets",
                "metered_providers", "default_model", "default_thinking"):
        assert key in data, key
    assert set(data["kinds"]) <= set(data["kind_harness"]), "every kind needs a kind_harness entry"
    assert {"T0", "T1", "T2", "T3", "T4"} == set(data["tiers"]) == set(data["thinking"])
    for path, chain in chains(data):
        assert all(isinstance(m, str) and "/" in m for m in chain), path
    if os.path.exists(PI_EXT):
        with open(PI_EXT) as fh:
            ts = fh.read()
        assert "CONFIG.kinds" in ts and "CONFIG.kind_harness" in ts and "CONFIG.tiers" in ts
    if os.path.exists(TOKYO_ZEN):
        assert os.access(TOKYO_ZEN, os.R_OK)
    # jdelegate loader (node): loads the file and routes a brief from it
    r = _jdelegate_dry_run()
    assert r.returncode == 0, r.stderr[-800:]
    assert "openrouter/" not in r.stdout
    # software-factory readers that do read it: model_health (quota_policy) and reviewpick (kinds.review)
    if os.path.exists(SF_ROOT) and os.path.exists(SF_PY):
        r = _sf("from control.model_health import Health\n"
                "p = Health().policy\nassert p['hot'] > p['warm'] > 0, p\n"
                "from control import reviewpick\n"
                "c = reviewpick._review_chains()\nassert c['T3'], c\nprint('ok')")
        assert r.returncode == 0 and "ok" in r.stdout, r.stderr[-800:]
        # router/route.py and router/auto.py do not read tiers.json: they must still import
        r = _sf("import router.route, router.auto\nprint('ok')")
        assert r.returncode == 0 and "ok" in r.stdout, r.stderr[-800:]


@pytest.mark.skipif(not os.path.exists(os.path.join(SF_ROOT, "control", "bin", "review-pick")), reason="SF_ROOT control/ not on this host")
def test_review_pick_check_tiers_passes():
    env = {**os.environ, "FACTORY_TIERS": PROPOSED}
    r = subprocess.run([os.path.join(SF_ROOT, "control", "bin", "review-pick"), "--check-tiers"],
                       capture_output=True, text=True, env=env, timeout=60)
    assert r.returncode == 0, (r.stdout + r.stderr)[-800:]


def _baseline_from_diff():
    """The pre-change file, rebuilt by reversing the diff on the proposal."""
    with tempfile.TemporaryDirectory() as t:
        out = os.path.join(t, "baseline.json")
        r = subprocess.run(["patch", "-R", "-s", "-o", out, PROPOSED, DIFF], capture_output=True, text=True)
        assert r.returncode == 0, r.stdout + r.stderr
        with open(out) as fh:
            return json.load(fh)


def test_diff_lists_every_changed_chain():
    with open(DIFF) as fh:
        diff_lines = fh.read().splitlines()
    removed = {ln[1:].strip().rstrip(",").strip('"') for ln in diff_lines if ln.startswith("-") and not ln.startswith("---")}
    added = {ln[1:].strip().rstrip(",").strip('"') for ln in diff_lines if ln.startswith("+") and not ln.startswith("+++")}
    old, new = _baseline_from_diff(), load()
    old_chains, new_chains = dict(chains(old)), dict(chains(new))
    changed = [p for p in sorted(set(old_chains) | set(new_chains)) if old_chains.get(p) != new_chains.get(p)]
    assert changed, "the diff changes no chain"
    for path in changed:
        a, b = old_chains.get(path, []), new_chains.get(path, [])
        for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b).get_opcodes():
            for m in a[i1:i2] if op in ("delete", "replace") else []:
                assert m in removed, f"{path}: removed entry {m} is not a '-' line of the diff"
            for m in b[j1:j2] if op in ("insert", "replace") else []:
                assert m in added, f"{path}: added entry {m} is not a '+' line of the diff"
    # the changes the packet names are all in the diff
    assert any(m.startswith("openrouter/") for m in removed)
    assert {"xai/grok-4.7", "gemini/gemini-3.8-flash"} <= added
    assert any(p.startswith("kinds.language.") for p in changed)
    assert {"kinds.research.T1", "kinds.doer_open.T1"} <= set(changed)
    assert "OG1 precondition: jdelegate must not append tiers.* for kind language (follow-up packet P6.08b)" in diff_lines
