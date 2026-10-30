#!/bin/bash
# kb-log-guard.sh — Stop hook (G11, warn only). If the session edited files (Edit/Write/MultiEdit/NotebookEdit)
# or ran `git commit` in a git repo that has no specs/_session/<today|yesterday>-tasks.md and the transcript has
# no `/kb-spec log` call, prints {"systemMessage":"kb-log-guard (G11): ..."} once per session per repo.
# Never blocks; exits 0 always.
set -u
in=""
[ -t 0 ] || in=$(cat 2>/dev/null || true)
[ -n "$in" ] || exit 0

CACHE="${KB_LOG_GUARD_CACHE:-$HOME/.cache/kb-log-guard}"
printf '%s' "$in" | KB_CACHE="$CACHE" python3 -c '
import json, os, re, sys, time

try:
    payload = json.load(sys.stdin)
except Exception:
    sys.exit(0)
if not isinstance(payload, dict):
    sys.exit(0)
tp = payload.get("transcript_path")
if not isinstance(tp, str) or not tp or not os.path.isfile(tp):
    sys.exit(0)
sid = payload.get("session_id")
sid = re.sub(r"[^A-Za-z0-9_.-]", "_", sid) if isinstance(sid, str) and sid else "nosession"
pcwd = payload.get("cwd") if isinstance(payload.get("cwd"), str) else ""
home = os.path.expanduser("~")
cache = os.environ["KB_CACHE"]

EDIT_TOOLS = {"Edit": "file_path", "Write": "file_path", "MultiEdit": "file_path", "NotebookEdit": "notebook_path"}

def git_root(p):
    if not p or not os.path.isabs(p):
        return None
    d = p if os.path.isdir(p) else os.path.dirname(p)
    while d and d != "/":
        if os.path.exists(os.path.join(d, ".git")):
            return d
        d = os.path.dirname(d)
    return None

def skipped(p):
    p = os.path.realpath(p) if os.path.exists(p) else p
    if p.startswith("/private/tmp/claude-") or p.startswith("/tmp/claude-"):
        return True
    cl = os.path.join(home, ".claude")
    if p == cl or p.startswith(cl + "/"):
        return True
    return False

repos = set()
logged = False

def add(path):
    if not path or skipped(path):
        return
    r = git_root(path)
    if r and not skipped(r):
        repos.add(r)

def commit_dirs(cmd, cwd):
    dirs = [cwd]
    for m in re.finditer(r"git\s+-C\s+(\"[^\"]+\"|\x27[^\x27]+\x27|\S+)", cmd):
        dirs.append(m.group(1).strip("\"\x27"))
    for m in re.finditer(r"\bcd\s+(\"[^\"]+\"|\x27[^\x27]+\x27|[^\s;&|]+)", cmd):
        dirs.append(m.group(1).strip("\"\x27"))
    out = []
    for d in dirs:
        d = d.replace("$HOME", home).replace("~", home, 1) if d.startswith(("~", "$HOME")) else d
        if d and not os.path.isabs(d) and cwd:
            d = os.path.join(cwd, d)
        out.append(d)
    return out

try:
    f = open(tp, "rb")
except Exception:
    sys.exit(0)
with f:
    for raw in f:
        # cheap prefilter before json parsing
        if (b"file_path" not in raw and b"notebook_path" not in raw and b"git commit" not in raw
                and b"kb-spec" not in raw):
            continue
        try:
            obj = json.loads(raw)
        except Exception:
            continue
        if not isinstance(obj, dict):
            continue
        msg = obj.get("message") if isinstance(obj.get("message"), dict) else obj
        role = msg.get("role") or obj.get("type")
        content = msg.get("content")
        lcwd = obj.get("cwd") if isinstance(obj.get("cwd"), str) else pcwd
        if isinstance(content, str):
            if role == "user" and "/kb-spec log" in content:
                logged = True
            continue
        if not isinstance(content, list):
            continue
        for b in content:
            if not isinstance(b, dict):
                continue
            t = b.get("type")
            if t == "text" and role == "user" and isinstance(b.get("text"), str) and "/kb-spec log" in b["text"]:
                logged = True
            elif t == "tool_use":
                name = b.get("name")
                inp = b.get("input") if isinstance(b.get("input"), dict) else {}
                if name in EDIT_TOOLS:
                    p = inp.get(EDIT_TOOLS[name])
                    if isinstance(p, str):
                        add(p)
                elif name == "Bash":
                    cmd = inp.get("command")
                    if isinstance(cmd, str) and "git commit" in cmd:
                        for d in commit_dirs(cmd, lcwd):
                            r = git_root(d)
                            if r:
                                add(r)
                                break
                elif name == "Skill":
                    sk = str(inp.get("skill", ""))
                    args = str(inp.get("args", "")).lstrip()
                    if "kb-spec" in sk and args.startswith("log"):
                        logged = True

if logged or not repos:
    sys.exit(0)

now = time.time()
days = [time.strftime("%Y-%m-%d", time.localtime(now)), time.strftime("%Y-%m-%d", time.localtime(now - 86400))]
missing = []
for r in sorted(repos):
    if not any(os.path.isfile(os.path.join(r, "specs", "_session", d + "-tasks.md")) for d in days):
        missing.append(r)

marker = os.path.join(cache, sid)
seen = set()
try:
    with open(marker) as mf:
        seen = set(l.rstrip("\n") for l in mf)
except Exception:
    pass
new = [r for r in missing if r not in seen]
if not new:
    sys.exit(0)
try:
    os.makedirs(cache, exist_ok=True)
    with open(marker, "a") as mf:
        for r in new:
            mf.write(r + "\n")
except Exception:
    pass
print(json.dumps({"systemMessage": "kb-log-guard (G11): files changed in " + ", ".join(new)
    + " but no /kb-spec log entry today. Run /kb-spec log \"<task>\"."}))
' 2>/dev/null || true
exit 0
