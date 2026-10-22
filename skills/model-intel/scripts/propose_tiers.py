#!/usr/bin/env python3
"""Propose (and, under strict conditions, auto-apply) tiers.json changes from data/latest.

Auto-apply only when ALL hold for a candidate:
  - not present anywhere in tiers.json yet (a newly available model) and reachable through a subscription provider
  - beats the incumbent head of that chain by >= 2 index points at <= its cost per task,
    or equal index (within 0.25) at <= 70% of its cost; not much slower (>= 70% of its tok/s)
  - slot is not owner-pinned (kinds.language/test/review chains, and the first two Opus/Sonnet entries of T3/T4); candidate satisfies the owner rules (no GPT outside review/language, no Opus worker)
  - passes a live probe
Applied = candidate inserted ahead of the incumbent (incumbent stays as fallback), after a .bak-model-intel-DATE
backup; validated with jq and the jdelegate dry-run, restored on failure. Everything else -> data/proposals/DATE.md.
Exit: 0 nothing applied, 2 applied, 1 error.   Usage: propose_tiers.py [--dry-run]  (--dry-run: no probe, no write)
Env: MODEL_INTEL_TIERS (tiers.json path), MODEL_INTEL_PROBE=ok|fail (test override), MODEL_INTEL_VALIDATE_CMD.
"""
import importlib.util, json, os, re, shutil, subprocess, sys
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mi, recommend

RULES = recommend.RULES
AUTO = RULES["auto_apply"]
EFFORT_FOR = {"off": ["non-reasoning", "minimal", "default", "low"], "minimal": ["minimal", "non-reasoning", "low"],
              "low": ["low", "minimal", "default"], "medium": ["medium", "default", "low"],
              "high": ["high", "default", "xhigh", "medium"], "xhigh": ["xhigh", "high"]}
PLAIN_KINDS_USE = {"language": "language", "review": "review"}
CREATOR_ONLY = {"language": "OpenAI", "review": "OpenAI"}  # owner: GPT only for review and language, and those chains are GPT


def pinned(tiers):
    """Whole-chain owner pins: owner_rules.json pinned_entries.chains plus an explicit tiers.json _pinned list.
    tiers.T2/T3/T4 are NOT pinned as sections; only their leading Claude entries are (pinned_prefix)."""
    return set(RULES["pinned_entries"]["chains"]) | set(tiers.get("_pinned", []))


def pinned_prefix(lst, tier):
    """Number of leading Opus/Sonnet Claude entries the owner pinned in a T3/T4 chain (first two slots)."""
    pe = RULES["pinned_entries"]
    if tier not in pe["claude_prefix_tiers"]:
        return 0
    n = 0
    for x in lst[:pe["claude_prefix_len"]]:
        if re.search(r"/claude-(opus|sonnet)", x):
            n += 1
        else:
            break
    return n


def chains(tiers):
    for t, lst in tiers.get("tiers", {}).items():
        yield f"tiers.{t}", t, "code", lst
    for k, per in tiers.get("kinds", {}).items():
        for t, lst in per.items():
            yield f"kinds.{k}.{t}", t, PLAIN_KINDS_USE.get(k, k if k != "code" else "code"), lst


def all_ids(tiers):
    ids = set()
    def walk(v):
        if isinstance(v, str) and "/" in v:
            ids.add(v)
        elif isinstance(v, list):
            [walk(x) for x in v]
        elif isinstance(v, dict):
            [walk(x) for k, x in v.items() if k not in ("_comment", "_notes", "_blocked")]
    walk(tiers)
    return ids


def at_effort(rows_by_key, key, want):
    fam = rows_by_key.get(key, [])
    for e in EFFORT_FOR.get(want, [want]):
        for r in fam:
            if r["effort"] == e:
                return r
    return None  # no listed level matches: skip rather than compare at a different effort


def decide(tiers, rows, reach, probe, today=None):
    """Pure decision: returns (auto, proposals). auto items carry chain/insert/before; proposals carry reason."""
    by_key = {}
    for r in rows:
        by_key.setdefault(r["key"], []).append(r)
    pins = pinned(tiers)
    metered = set(tiers.get("metered_providers", []))
    blocked = set(tiers.get("_blocked", {}))
    present = all_ids(tiers)
    auto, props = [], []
    cands_all = []
    for key, e in reach["models"].items():
        cands_all.append((key, e))
    for chain, tier, use, lst in chains(tiers):
        want = tiers.get("thinking", {}).get(tier, "medium")
        npin = pinned_prefix(lst, tier)
        has_row = lambda x: recommend.mkey(recommend.split_id(x)[1]) in by_key
        head = next((x for x in lst[npin:] if has_row(x)), None)
        slot_pinned = head is None
        if head is None:  # every scored entry is pinned: compare against the pinned head, proposal only
            head = next((x for x in lst if has_row(x)), None)
        if head is None:
            continue
        inc = at_effort(by_key, recommend.mkey(recommend.split_id(head)[1]), want)
        if inc is None or inc["cost"] is None:
            continue
        best, fallback = None, None
        for key, e in cands_all:
            if key == inc["key"] or key not in by_key:
                continue
            c = at_effort(by_key, key, want)
            if c is None or c["cost"] is None:
                continue
            c = dict(c, reach=e)
            if not recommend.allowed(c, use) or CREATOR_ONLY.get(use, c["creator"]) != c["creator"]:
                continue
            gain = c["index"] - inc["index"]
            qual = (gain >= AUTO["min_index_gain"] and c["cost"] <= inc["cost"]) or \
                   (abs(gain) <= AUTO["equal_index_tolerance"] and c["cost"] <= AUTO["equal_index_cost_ratio"] * inc["cost"])
            better = lambda x, y: y is None or (x["index"], -x["cost"]) > (y["index"], -y["cost"])
            if qual and better(c, best):
                best = c
            elif not qual and gain > 0 and c["cost"] <= inc["cost"] and better(c, fallback):
                fallback = c  # better and no dearer, but under the auto-apply margin: owner proposal only
        best = best or fallback
        if best is None:
            continue
        e = best["reach"]
        sub = next((p for p in e["providers"] if p["subscription"] and p["provider"] not in metered and p["id"] not in blocked), None)
        gain = best["index"] - inc["index"]
        qualifies = (gain >= AUTO["min_index_gain"] and best["cost"] <= inc["cost"]) or \
                    (abs(gain) <= AUTO["equal_index_tolerance"] and best["cost"] <= AUTO["equal_index_cost_ratio"] * inc["cost"])
        no_speed = not (best["tps"] and inc["tps"])
        slow = bool(not no_speed and best["tps"] < 0.7 * inc["tps"])
        info = {"chain": chain, "tier": tier, "incumbent": head, "inc_model": inc["base"], "inc_index": inc["index"],
                "inc_cost": inc["cost"], "inc_tps": inc["tps"], "candidate": best["base"], "effort": best["effort"],
                "index": best["index"], "cost": best["cost"], "tps": best["tps"], "gain": round(gain, 2)}
        reasons = []
        if any(chain == p or chain.startswith(p + ".") for p in pins):
            reasons.append("owner-pinned chain")
        if slot_pinned:
            reasons.append("owner-pinned entry (no free slot)")
        if sub is None:
            reasons.append("metered-only (no subscription provider)")
        else:
            info["insert"] = sub["id"]
            if sub["id"] in present or any(p["id"] in present for p in e["providers"]):
                reasons.append("already in tiers.json: reorder is the owner's call")
        if not qualifies:
            reasons.append("below auto-apply margin")
        if slow:
            reasons.append(f"much slower ({best['tps']:.0f} vs {inc['tps']:.0f} tok/s)")
        elif no_speed:
            reasons.append("speed data missing")
        if not reasons and sub is not None:
            if probe is None:  # --dry-run: no live provider call; report what a real run would try
                props.append(dict(info, reason="dry-run: would probe, then auto-apply if it passes"))
                continue
            try:
                ok = probe(sub["id"])
            except Exception as e:  # pi missing, timeout, ...: a failed probe, not a crashed run
                print(f"propose: probe {sub['id']} raised {type(e).__name__}: {e}", file=sys.stderr)
                ok = False
            if ok:
                auto.append(info)
                continue
            reasons.append("live probe failed")
        props.append(dict(info, reason="; ".join(reasons)))
    return auto, props


def cap_changes(auto):
    return auto[:AUTO["max_changes_per_run"]]


def claude_count(lst):
    return sum(1 for x in lst if x.startswith("cliproxy/claude") or "/claude-" in x)


def backup_path(path, today):
    """A backup name not used yet: .bak-model-intel-DATE, then -DATE.2, -DATE.3 ... (never overwrites one)."""
    first = path.with_name(path.name + f".bak-model-intel-{today}")
    if not first.exists():
        return first
    n = 2
    while first.with_name(f"{first.name}.{n}").exists():
        n += 1
    return first.with_name(f"{first.name}.{n}")


def apply_changes(path, auto, today):
    """Back up, insert candidates ahead of the incumbent, validate, restore on failure. Returns backup path.
    Every apply writes its own fresh backup of the file as it is right now, so a failed second run on the same
    day restores that run's starting point, not the morning's file (which would undo the earlier apply)."""
    path = Path(path)
    backup = backup_path(path, today)
    shutil.copy2(path, backup)
    tiers = json.loads(path.read_text())
    before = {c: claude_count(l) for c, _, _, l in chains(tiers)}
    notes = []
    for a in auto:
        lst = next(l for c, _, _, l in chains(tiers) if c == a["chain"])
        if a["insert"] in lst:
            continue
        lst.insert(lst.index(a["incumbent"]), a["insert"])
        notes.append(f"{a['insert']} ahead of {a['incumbent']} in {a['chain']} (index {a['index']} vs {a['inc_index']}, "
                     f"cost/task ${a['cost']:.3f} vs ${a['inc_cost']:.3f})")
    for c, _, _, l in chains(tiers):
        assert claude_count(l) >= before[c], f"would remove a Claude entry from {c}"
    if isinstance(tiers.get("_comment"), list) and notes:
        tiers["_comment"].append(f"{today} model-intel auto-apply (backup {backup.name}): " + "; ".join(notes))
    tmp = path.with_name(path.name + ".model-intel.tmp")
    tmp.write_text(json.dumps(tiers, indent=2, ensure_ascii=False) + "\n")
    os.replace(tmp, path)
    try:
        err = validate(path)
    except Exception:
        shutil.copy2(backup, path)
        raise
    if err:
        shutil.copy2(backup, path)
        raise RuntimeError(f"validation failed, restored backup: {err}")
    return backup


def validate(path):
    r = subprocess.run(["jq", "empty", str(path)], capture_output=True, text=True)
    if r.returncode:
        return "jq: " + r.stderr.strip()
    cmd = os.environ.get("MODEL_INTEL_VALIDATE_CMD")
    if cmd is None and Path(path).resolve() == mi.REAL_TIERS.resolve():
        jd = shutil.which("jdelegate") or str(Path.home() / "code/dev-stack/bin/jdelegate")
        cmd = f"{jd} --dry-run --no-tab --no-auto-mcp --no-auto-skill --no-auto-role --cwd /tmp 'model-intel validation ping'"
    if cmd:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60)
        if r.returncode:
            return f"validate cmd rc={r.returncode}: {(r.stderr or r.stdout).strip()[:200]}"
    return None


def default_probe(model):
    forced = os.environ.get("MODEL_INTEL_PROBE")
    if forced:
        return forced == "ok"
    p = Path.home() / ".pi/agent/skills/model-health/probe.py"
    if p.exists():
        spec = importlib.util.spec_from_file_location("mh_probe", p)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return bool(m.probe(model).get("ok"))
    r = subprocess.run(["pi", "--mode", "json", "-p", "--no-tools", "--thinking", "off", "--model", model, "Reply OK"],
                       capture_output=True, text=True, timeout=90, stdin=subprocess.DEVNULL)
    return r.returncode == 0 and '"agent_end"' in r.stdout and '"stopReason":"error"' not in r.stdout


def render(today, auto, props, applied, backup):
    L = [f"# Tier proposals {today}", ""]
    L.append(f"Applied automatically: {len(applied)}" + (f" (backup `{backup}`)" if backup else ""))
    for a in applied:
        L.append(f"- `{a['chain']}`: inserted `{a['insert']}` ahead of `{a['incumbent']}` "
                 f"(index {a['index']:.1f} vs {a['inc_index']:.1f}, cost/task ${a['cost']:.3f} vs ${a['inc_cost']:.3f})")
    L += ["", f"For the owner: {len(props)}"]
    for p in sorted(props, key=lambda x: -x["gain"]):
        L.append(f"- `{p['chain']}`: {p['candidate']} ({p['effort']}) index {p['index']:.1f} cost ${p['cost']:.3f} vs "
                 f"{p['inc_model']} {p['inc_index']:.1f} ${p['inc_cost']:.3f} (gain {p['gain']:+.1f}). Not applied: {p['reason']}."
                 + (f" Would insert `{p['insert']}`." if p.get("insert") else ""))
    return "\n".join(L) + "\n"


def main(argv):
    dry = "--dry-run" in argv
    if not mi.TIERS.exists():
        print(f"propose: {mi.TIERS} not found", file=sys.stderr)
        return 1
    if mi.latest_dir() is None:
        print("propose: no snapshot", file=sys.stderr)
        return 1
    tiers = json.load(open(mi.TIERS))
    reach = recommend.build_reachable()
    rows = recommend.load_llm(reach)
    auto, props = decide(tiers, rows, reach, None if dry else default_probe)
    auto = cap_changes(auto)
    applied, backup = [], None
    if auto and not dry:
        try:
            backup = apply_changes(mi.TIERS, auto, mi.today())
            applied = auto
        except Exception as e:
            print(f"propose: apply failed: {e}", file=sys.stderr)
            for a in auto:
                props.append(dict(a, reason=f"apply failed: {e}"))
    elif auto:
        for a in auto:
            props.append(dict(a, reason="dry-run: would auto-apply"))
    out = mi.DATA / "proposals"
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{mi.today()}.md").write_text(render(mi.today(), auto, props, applied, backup))
    print(f"applied={len(applied)} proposals={len(props)} -> {out / (mi.today() + '.md')}")
    return 2 if applied else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
