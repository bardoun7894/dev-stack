#!/usr/bin/env python3
"""capability-scan — incremental scan of Claude Code transcripts into usage events.

Reads ~/.claude/projects/**/*.jsonl (incl. <session>/subagents/agent-*.jsonl) line by line (binary, cheap regex pre-filter before json.loads), remembers a
byte offset per file in <state>/scan-state.json, and appends to <state>/usage.jsonl:
  {ts, session, project, kind: skill|agent|mcp, name, via: skill-tool|parked-read|agent-tool|jdelegate|mcp-tool,
   prompt, seq[, sub: true]}
and to <state>/turns.jsonl one record per real user prompt: {ts, session, project, seq, prompt}
Sub-agent events carry sub:true and the parent session id (the directory name); they add no turns.
(turns let capability-outcomes.py tell "nothing used" from "session ended").
Also folds in ~/.cache/jdelegate/<run>/: "## Role: x" / "## Skill: x" in worker-prompt.md (claude workers) or in the
worker prompt ahead of "--- TASK ---" in brief.md (other harnesses); the recorded prompt is the task text.

  capability-scan.py [--days N] [--rebuild]
Env: DEVSTACK_STATE (default ~/.local/state/dev-stack), CLAUDE_PROJECTS_DIR, JDELEGATE_CACHE_DIR (or JDELEGATE_CACHE, as jdelegate names it).
"""
import glob
import json
import os
import re
import sys
import time
from datetime import datetime, timezone

PROMPT_CHARS = 300
FILTER = re.compile(rb"Skill|subagent_type|skills-parked|agents-parked|mcp__")
PARKED_SKILL = re.compile(r"skills-parked/([^/\s'\"]+)/SKILL\.md")
PARKED_AGENT = re.compile(r"agents-parked/([^/\s'\"]+?)\.md")
REMINDER = re.compile(r"<system-reminder>.*?</system-reminder>", re.S)
JD_SKILL = re.compile(r"^## Skill: (\S+)", re.M)
JD_ROLE = re.compile(r"^## Role: (\S+)", re.M)
TASK_MARKER = "\n--- TASK ---\n"


def state_dir():
    return os.environ.get("DEVSTACK_STATE") or os.path.expanduser("~/.local/state/dev-stack")


def projects_dir():
    return os.environ.get("CLAUDE_PROJECTS_DIR") or os.path.expanduser("~/.claude/projects")


def jdelegate_dir():
    return os.environ.get("JDELEGATE_CACHE_DIR") or os.environ.get("JDELEGATE_CACHE") or os.path.expanduser("~/.cache/jdelegate")


def parse_ts(s):
    try:
        return int(datetime.strptime(s[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc).timestamp())
    except (ValueError, TypeError):
        return 0


def prompt_text(msg):
    """Text of a real user prompt, or '' for tool results / empty."""
    c = msg.get("content")
    if isinstance(c, str):
        text = c
    elif isinstance(c, list):
        if any(isinstance(b, dict) and b.get("type") == "tool_result" for b in c):
            return ""
        text = "\n".join(b.get("text", "") for b in c if isinstance(b, dict) and b.get("type") == "text")
    else:
        return ""
    return REMINDER.sub("", text).strip()


def tool_events(block):
    """[(kind, name, via)] for one assistant tool_use block."""
    name, inp = block.get("name", ""), block.get("input") or {}
    out = []
    if name == "Skill" and isinstance(inp.get("skill"), str):
        out.append(("skill", inp["skill"], "skill-tool"))
    elif name in ("Agent", "Task") and isinstance(inp.get("subagent_type"), str):
        out.append(("agent", inp["subagent_type"], "agent-tool"))
    elif name.startswith("mcp__"):
        out.append(("mcp", name.split("__")[1] if name.count("__") >= 2 else name[5:], "mcp-tool"))
    if name in ("Read", "Bash", "Grep", "Glob"):
        text = inp.get("file_path") or inp.get("command") or inp.get("path") or ""
        if isinstance(text, str):
            out += [("skill", m, "parked-read") for m in PARKED_SKILL.findall(text)]
            out += [("agent", m, "parked-read") for m in PARKED_AGENT.findall(text)]
    return out


def scan_file(path, st, project, cutoff, usage, turns, parent=None):
    """Read new complete lines; st = {off, seq, prompt, mtime}. Returns number of events."""
    n = 0
    sub_file = parent is not None
    with open(path, "rb") as f:
        f.seek(st["off"])
        while True:
            line = f.readline()
            if not line.endswith(b"\n"):
                break
            st["off"] += len(line)
            is_user = b'"type":"user"' in line and b"tool_use_id" not in line
            if not is_user and not FILTER.search(line):
                continue
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if d.get("isMeta"):
                continue
            sub = sub_file or bool(d.get("isSidechain"))
            ts = parse_ts(d.get("timestamp", ""))
            session = parent or d.get("sessionId") or os.path.basename(path)[:-6]
            msg = d.get("message")
            if not isinstance(msg, dict):
                continue
            if d.get("type") == "user":
                if sub:
                    continue
                text = prompt_text(msg)
                if text and not text.startswith("<command-name>") and not text.startswith("<local-command"):
                    st["prompt"] = text[:PROMPT_CHARS]
                    st["seq"] += 1
                    if ts >= cutoff:
                        turns.append({"ts": ts, "session": session, "project": project, "seq": st["seq"] - 1,
                                      "prompt": st["prompt"]})
                continue
            if d.get("type") != "assistant" or ts < cutoff or not isinstance(msg.get("content"), list):
                continue
            for block in msg["content"]:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    for kind, name, via in tool_events(block):
                        row = {"ts": ts, "session": session, "project": project, "kind": kind, "name": name,
                               "via": via, "prompt": st.get("prompt", ""), "seq": max(st["seq"] - 1, 0)}
                        if sub:
                            row["sub"] = True
                        usage.append(row)
                        n += 1
    return n


def jdelegate_text(path):
    try:
        with open(path, errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def scan_jdelegate(root, state, cutoff, usage):
    """One usage row per skill/role a jdelegate run inlined. Claude workers keep the worker prompt in
    worker-prompt.md and the task alone in brief.md; the other harnesses get the worker prompt prepended to
    brief.md ahead of a `--- TASK ---` line, so the task is the text after it."""
    done = state.setdefault("jdelegate", {})
    n = 0
    for run in sorted(glob.glob(os.path.join(root, "*"))):
        marker = os.path.join(run, "run.sh")
        try:
            mtime = os.path.getmtime(marker)
        except OSError:
            continue
        if done.get(run) == mtime or mtime < cutoff:
            continue
        done[run] = mtime
        worker_prompt = jdelegate_text(os.path.join(run, "worker-prompt.md"))
        brief = jdelegate_text(os.path.join(run, "brief.md"))
        head, sep, task = brief.partition(TASK_MARKER)
        if sep:
            worker_prompt += "\n" + head
        else:
            task = brief
        names = [("agent", m) for m in JD_ROLE.findall(worker_prompt)] + [("skill", m) for m in JD_SKILL.findall(worker_prompt)]
        prompt = REMINDER.sub("", task).strip()[:PROMPT_CHARS]
        for kind, name in dict.fromkeys(names):
            usage.append({"ts": int(mtime), "session": "jdelegate:" + os.path.basename(run), "project": "jdelegate",
                          "kind": kind, "name": name, "via": "jdelegate", "prompt": prompt, "seq": 0})
            n += 1
    return n



def locate(projects, path):
    """(project, parent session id or None) for a transcript path under projects/."""
    parts = os.path.relpath(path, projects).split(os.sep)
    if "subagents" in parts[:-1] and len(parts) >= 4:
        return parts[0], parts[1]
    return parts[0], None


def scan(projects=None, state=None, days=None, rebuild=False, jdelegate=None, now=None):
    projects = projects or projects_dir()
    sdir = state or state_dir()
    os.makedirs(sdir, exist_ok=True)
    now = now or time.time()
    cutoff = now - days * 86400 if days else 0
    paths = {k: os.path.join(sdir, k) for k in ("usage.jsonl", "turns.jsonl", "scan-state.json")}
    if rebuild:
        for p in paths.values():
            if os.path.exists(p):
                os.remove(p)
    try:
        with open(paths["scan-state.json"]) as f:
            state_doc = json.load(f)
    except (OSError, ValueError):
        state_doc = {}
    files_state = state_doc.setdefault("files", {})
    usage, turns, stats = [], [], {"files": 0, "events": 0, "turns": 0}
    for path in glob.glob(os.path.join(projects, "**", "*.jsonl"), recursive=True):
        try:
            stt = os.stat(path)
        except OSError:
            continue
        st = files_state.get(path)
        if st and st["off"] == stt.st_size and st["mtime"] == stt.st_mtime:
            continue
        if st is None and cutoff and stt.st_mtime < cutoff:
            continue
        if st is None or stt.st_size < st["off"]:
            st = {"off": 0, "seq": 0, "prompt": "", "mtime": 0}
        files_state[path] = st
        stats["files"] += 1
        project, parent = locate(projects, path)
        try:
            scan_file(path, st, project, cutoff, usage, turns, parent)
        except OSError:
            continue
        st["mtime"] = stt.st_mtime
    jd = jdelegate or jdelegate_dir()
    if os.path.isdir(jd):
        scan_jdelegate(jd, state_doc, cutoff, usage)
    for name, rows in (("usage.jsonl", usage), ("turns.jsonl", turns)):
        if rows:
            with open(paths[name], "a") as f:
                f.write("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    stats["events"], stats["turns"] = len(usage), len(turns)
    tmp = paths["scan-state.json"] + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state_doc, f)
    os.replace(tmp, paths["scan-state.json"])
    return stats


def main(argv):
    days, rebuild = None, "--rebuild" in argv
    if "--days" in argv:
        days = float(argv[argv.index("--days") + 1])
    t = time.time()
    s = scan(days=days, rebuild=rebuild)
    print(f"scanned {s['files']} files, {s['events']} events, {s['turns']} turns in {time.time() - t:.1f}s")


if __name__ == "__main__":
    main(sys.argv[1:])
