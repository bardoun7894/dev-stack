#!/usr/bin/env python3
"""capability-registry — one JSON view of every skill / agent / MCP server with its real usage.

Builds <state>/capabilities.json from usage.jsonl (capability-scan.py), the installed skill/agent/MCP
definitions, and skill-suggest outcomes (capability-outcomes.py) in the Jev decision log.

  capability-registry.py [build]       write capabilities.json
  capability-registry.py report        compact table sorted by uses_30d
  capability-registry.py park-plan <policy.json>   moves park-skills.sh auto should make (one per line)

Env: DEVSTACK_STATE, CLAUDE_HOME (default ~/.claude), CLAUDE_JSON (default ~/.claude.json), JEV_LOG_DIR.
"""
import glob
import importlib.machinery
import importlib.util
import json
import os
import re
import sys
import time
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.realpath(__file__))
SUGGEST_TAG = "skill-suggest"
RERANK_PREFIX = "Which of these skills"


def state_dir():
    return os.environ.get("DEVSTACK_STATE") or os.path.expanduser("~/.local/state/dev-stack")


def claude_home():
    return os.environ.get("CLAUDE_HOME") or os.path.expanduser("~/.claude")


def _frontmatter():
    loader = importlib.machinery.SourceFileLoader("jev_skill_suggest_fm", os.path.join(HERE, "..", "bin", "jev-skill-suggest"))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod.frontmatter


def read_fm(path, frontmatter):
    try:
        with open(path, encoding="utf-8") as f:
            return frontmatter(f.read())
    except OSError:
        return {}


def discover(home, claude_json, frontmatter):
    """{key: {kind, name, description, location, path}} for installed skills, agents and MCP servers."""
    found = {}

    def add(kind, name, desc, location, path=""):
        found.setdefault(f"{kind}:{name}", {"kind": kind, "name": name, "description": desc, "location": location, "path": path})

    for location, sub in (("live", "skills"), ("parked", "skills-parked")):
        for p in sorted(glob.glob(os.path.join(home, sub, "*", "SKILL.md"))):
            fm = read_fm(p, frontmatter)
            name = os.path.basename(os.path.dirname(p))
            add("skill", fm.get("name") or name, fm.get("description", ""), location, os.path.dirname(p))
    for plugin in sorted(glob.glob(os.path.join(home, "plugins", "cache", "*", "*"))):
        versions = sorted(glob.glob(os.path.join(plugin, "*")), key=os.path.getmtime)
        if versions:
            for p in sorted(glob.glob(os.path.join(versions[-1], "skills", "*", "SKILL.md"))):
                fm = read_fm(p, frontmatter)
                name = fm.get("name") or os.path.basename(os.path.dirname(p))
                add("skill", os.path.basename(plugin) + ":" + name, fm.get("description", ""), "live", os.path.dirname(p))
    for location, sub in (("live", "agents"), ("parked", "agents-parked")):
        for p in sorted(glob.glob(os.path.join(home, sub, "*.md"))):
            fm = read_fm(p, frontmatter)
            add("agent", os.path.basename(p)[:-3], fm.get("description", ""), location, p)
    servers = []
    try:
        with open(claude_json) as f:
            cj = json.load(f)
    except (OSError, ValueError):
        cj = {}
    servers += list((cj.get("mcpServers") or {}))
    mcp_files = []
    for proj, cfg in (cj.get("projects") or {}).items():
        if isinstance(cfg, dict):
            servers += list(cfg.get("mcpServers") or {})
        mcp_files.append(os.path.join(proj, ".mcp.json"))
    mcp_files.append(os.path.join(os.getcwd(), ".mcp.json"))
    for mf in mcp_files:
        try:
            with open(mf) as f:
                servers += list((json.load(f).get("mcpServers") or {}))
        except (OSError, ValueError, AttributeError):
            pass
    for s in dict.fromkeys(servers):
        add("mcp", s, "", "live")
    return found


def read_usage(state):
    try:
        with open(os.path.join(state, "usage.jsonl")) as f:
            for line in f:
                try:
                    yield json.loads(line)
                except ValueError:
                    continue
    except OSError:
        return


def read_precision():
    """{name: [suggested_n, followed_n]} from shown rerank decisions that carry an outcome."""
    sys.path.insert(0, os.path.join(HERE, ".."))
    base = os.environ.get("JEV_LOG_DIR") or os.path.expanduser("~/.local/state/jev")
    path = os.path.join(base, "decisions.jsonl")
    decisions, outcomes = {}, {}
    try:
        with open(path) as f:
            for line in f:
                if '"outcome"' not in line and RERANK_PREFIX not in line:
                    continue
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if r.get("kind_of_record") == "outcome":
                    outcomes[r["id"]] = r["outcome"]
                elif r.get("tag") == SUGGEST_TAG and str((r.get("question") or {}).get("instructions", "")).startswith(RERANK_PREFIX):
                    decisions[r["id"]] = r.get("value")
    except OSError:
        return {}
    out = {}
    for did, value in decisions.items():
        if did in outcomes and value:
            c = out.setdefault(value, [0, 0])
            c[0] += 1
            c[1] += outcomes[did] == value
    return out


def iso(ts):
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def norm(s):
    return re.sub(r"\s+", " ", s).strip().lower()[:80]


def build(state=None, home=None, claude_json=None, now=None):
    state = state or state_dir()
    home = home or claude_home()
    claude_json = claude_json or os.environ.get("CLAUDE_JSON") or os.path.expanduser("~/.claude.json")
    now = now or time.time()
    items = discover(home, claude_json, _frontmatter())
    agg = {}
    for e in read_usage(state):
        key = f"{e.get('kind')}:{e.get('name')}"
        agg.setdefault(key, []).append(e)
    precision = read_precision()
    for key, evs in agg.items():
        if key not in items and evs[0].get("kind") == "mcp":
            items[key] = {"kind": "mcp", "name": evs[0]["name"], "description": "", "location": "external", "path": ""}
    for key, it in items.items():
        evs = sorted(agg.get(key, []), key=lambda e: e.get("ts", 0), reverse=True)
        age = lambda e: (now - e.get("ts", 0)) / 86400
        it["uses_7d"] = sum(1 for e in evs if age(e) <= 7)
        it["uses_14d"] = sum(1 for e in evs if age(e) <= 14)
        it["uses_30d"] = sum(1 for e in evs if age(e) <= 30)
        it["uses_total"] = len(evs)
        it["last_used"] = iso(evs[0]["ts"]) if evs else None
        counts = {}
        for e in evs:
            if age(e) <= 30:
                counts[e.get("project", "")] = counts.get(e.get("project", ""), 0) + 1
        it["projects"] = [p for p, _ in sorted(counts.items(), key=lambda kv: -kv[1])[:3]]
        seen, ex = set(), []
        for e in evs:
            p = (e.get("prompt") or "").strip()
            if p and norm(p) not in seen:
                seen.add(norm(p))
                ex.append(p[:300])
                if len(ex) == 3:
                    break
        it["examples"] = ex
        pkey = it["name"] if it["kind"] == "skill" else ("agent:" + it["name"] if it["kind"] == "agent" else None)
        s, fol = precision.get(pkey, [0, 0]) if pkey else (0, 0)
        it["suggested_n"], it["followed_n"] = s, fol
        it["precision"] = round(fol / s, 3) if s else None
    return {"generated": iso(now), "items": dict(sorted(items.items()))}


def write(reg, state=None):
    state = state or state_dir()
    os.makedirs(state, exist_ok=True)
    path = os.path.join(state, "capabilities.json")
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(reg, f, indent=1, ensure_ascii=False)
    os.replace(tmp, path)
    return path


def report(reg):
    rows = sorted(reg["items"].values(), key=lambda i: (-i.get("uses_30d", 0), i["kind"], i["name"]))
    w = max([len(i["name"]) for i in rows] + [4])
    lines = [f"{'kind':<6} {'name':<{w}} {'location':<8} {'uses_30d':>8} {'last_used':<10} {'precision':>9}"]
    for i in rows:
        p = i.get("precision")
        lines.append(f"{i['kind']:<6} {i['name']:<{w}} {i['location']:<8} {i.get('uses_30d', 0):>8} "
                     f"{(i.get('last_used') or '-')[:10]:<10} {('-' if p is None else format(p, '.2f')):>9}")
    return "\n".join(lines)


def park_plan(reg, policy, home):
    """Lines: 'park|unpark <kind> <name>' or 'real <kind> <name> <where>'. Plugin skills and MCP are never moved."""
    pins = {"skill": set(policy.get("pin_skills", [])), "agent": set(policy.get("pin_agents", []))}
    need = policy.get("keep_if_uses_14d_at_least", 3)
    out = []
    for it in reg["items"].values():
        kind, name = it["kind"], it["name"]
        if kind not in pins or ":" in name or it["location"] not in ("live", "parked"):
            continue
        want_live = name in pins[kind] or it.get("uses_14d", 0) >= need
        if want_live == (it["location"] == "live"):
            continue
        # the directory name is what moves; the frontmatter name may differ from it
        dirname = os.path.basename(it["path"]) if kind == "skill" and it.get("path") else name
        if not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9._-]*", dirname):
            continue
        sub = ("skills" if kind == "skill" else "agents") + ("" if it["location"] == "live" else "-parked")
        path = os.path.join(home, sub, dirname if kind == "skill" else name + ".md")
        if os.path.exists(path) and not os.path.islink(path):
            out.append(f"real {kind} {dirname} {'real directory' if os.path.isdir(path) else 'real file'} (left alone)")
            continue
        out.append(f"{'park' if it['location'] == 'live' else 'unpark'} {kind} {dirname if kind == 'skill' else name}")
    return out


def check_usage_evidence(state=None):
    """Parking by use is meaningless without use data: raise unless usage.jsonl has events and the scan read files."""
    sd = state or state_dir()
    if not os.path.exists(os.path.join(sd, "usage.jsonl")) or os.path.getsize(os.path.join(sd, "usage.jsonl")) == 0:
        raise ValueError("usage.jsonl is missing or empty, so nothing is known about what is used (run bin/capability-refresh)")
    with open(os.path.join(sd, "scan-state.json")) as f:
        if not json.load(f).get("files"):
            raise ValueError("the last scan covered 0 files (run bin/capability-refresh)")


def load_registry(state=None):
    with open(os.path.join(state or state_dir(), "capabilities.json")) as f:
        return json.load(f)


def main(argv):
    cmd = argv[0] if argv else "build"
    if cmd == "report":
        try:
            print(report(load_registry()))
        except (OSError, ValueError, KeyError) as e:
            print(f"no registry yet: {e}", file=sys.stderr)
            return 1
    elif cmd == "park-plan":
        try:
            check_usage_evidence()
            reg = load_registry()
            with open(argv[1]) as f:
                policy = json.load(f)
        except (OSError, ValueError, IndexError) as e:
            print(f"cannot plan: {e}", file=sys.stderr)
            return 1
        print("\n".join(park_plan(reg, policy, claude_home())))
    elif cmd == "build":
        reg = build()
        write(reg)
        print(f"{len(reg['items'])} capabilities")
    else:
        print(__doc__)
        return 64
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
