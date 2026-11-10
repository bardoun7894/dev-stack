#!/usr/bin/env python3
"""specs.py: a project's specs as they are on a git ref, never the working tree (other agents edit those). Stdlib only.

  specs.py                     every factory project and its spec count
  specs.py PROJECT [--json]    one row per specs/NNN-*: tasks done/total, merged stamp
  specs.py PROJECT NNN         that spec's title, stamp and its open tasks
  --ref REF                    read this ref (default: preview_watch_branch, else <remote>/<main> after a fetch)

Projects come from $FACTORY_PROJECTS, else $FACTORY_CONTROL_DIR/projects.json, else ~/.factory-control/projects.json.
Exit 0 ok, 2 bad input or unknown project/spec.
"""
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

SPEC_DIR = re.compile(r"^(\d{3})-[\w.-]+$")
MERGED = re.compile(r"—\s*MERGED|\*\*Merged\*\*:\s*`?[0-9a-f]{7}", re.I)


def projects_file() -> Path:
    if os.environ.get("FACTORY_PROJECTS"):
        return Path(os.environ["FACTORY_PROJECTS"])
    return Path(os.environ.get("FACTORY_CONTROL_DIR") or Path.home() / ".factory-control") / "projects.json"


def load_projects() -> list:
    data = json.loads(projects_file().read_text())
    return data.get("projects", data) if isinstance(data, dict) else data


def git(path, *args):
    return subprocess.run(["git", "-C", str(path), *args], capture_output=True, text=True)


def ref_for(p: dict, ref) -> str:
    if ref:
        return ref
    if p.get("preview_watch_branch"):
        return p["preview_watch_branch"]
    remote, main = p.get("remote") or "origin", p.get("main") or "main"
    git(p["path"], "fetch", "-q", remote, main)  # a failed fetch keeps the last known ref
    return f"{remote}/{main}"


def show(path, ref, rel) -> str:
    r = git(path, "show", f"{ref}:{rel}")
    return r.stdout if r.returncode == 0 else ""


def spec_rows(p: dict, ref: str) -> list:
    r = git(p["path"], "ls-tree", "--name-only", f"{ref}:specs")
    if r.returncode != 0:
        return []
    rows = []
    for name in sorted(r.stdout.split()):
        m = SPEC_DIR.match(name)
        if not m:
            continue
        spec = show(p["path"], ref, f"specs/{name}/spec.md")
        tasks = show(p["path"], ref, f"specs/{name}/tasks.md")
        title = next((ln.lstrip("# ").strip() for ln in spec.splitlines() if ln.startswith("# ")), name)
        done = len(re.findall(r"(?m)^\s*- \[x\]", tasks, re.I))
        open_ = len(re.findall(r"(?m)^\s*- \[ \]", tasks))
        rows.append({"nnn": m.group(1), "dir": name, "title": title, "done": done, "total": done + open_,
                     "merged": bool(MERGED.search(spec))})
    return rows


def find(name: str) -> dict:
    for p in load_projects():
        if p.get("name") == name:
            return p
    print(f"unknown project: {name}", file=sys.stderr)
    sys.exit(2)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="specs.py")
    ap.add_argument("project", nargs="?")
    ap.add_argument("nnn", nargs="?")
    ap.add_argument("--ref")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    if not a.project:
        for p in load_projects():
            rows = spec_rows(p, ref_for(p, a.ref)) if Path(p.get("path", "")).is_dir() else []
            print(f"{p['name']:<16} {len(rows)} specs  intake={'on' if p.get('issue_intake') else 'off'}")
        return 0
    p = find(a.project)
    ref = ref_for(p, a.ref)
    rows = spec_rows(p, ref)
    if a.nnn:
        row = next((r for r in rows if r["nnn"] == a.nnn.zfill(3)), None)
        if not row:
            print(f"no spec {a.nnn} in {a.project} at {ref}", file=sys.stderr)
            return 2
        tasks = show(p["path"], ref, f"specs/{row['dir']}/tasks.md")
        print(f"{row['title']}  ({row['dir']} @ {ref})  tasks {row['done']}/{row['total']}  "
              f"{'merged' if row['merged'] else 'not merged'}")
        opens = [ln.strip() for ln in tasks.splitlines() if re.match(r"^\s*- \[ \]", ln)]
        print("open tasks:" if opens else "no open tasks")
        for ln in opens:
            print(f"  {ln}")
        return 0
    if a.json:
        print(json.dumps(rows, ensure_ascii=False))
        return 0
    print(f"{a.project} specs @ {ref}")
    for r in rows:
        state = "merged" if r["merged"] else ""
        print(f"  {r['nnn']}  {r['title'][:60]:<60}  {r['done']}/{r['total']}  {state}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
