#!/usr/bin/env python3
"""sweep.py <repo> [--memory DIR] [--no-gh]: list stale-context CANDIDATES for the direction --sweep pass. Zero AI.

Report only: it never edits, moves or deletes anything. Every line is a claim with its evidence, for an independent
verifier to confirm (AI LABS / Google "side quests", 2026-11-17). Candidates:
  NOTE-CLOSED   a TODO/FIXME/XXX/HACK line that names an issue (#123 or a GitHub issue URL) which is closed
  NOTE-OLD      a TODO/FIXME line untouched for more than 365 days (git blame), with no issue reference
  DOC-PATH      CLAUDE.md / AGENTS.md / README.md (repo root and docs/) names a backticked repo path that does not exist
  MEMORY-PATH   a memory note (--memory DIR, *.md) names a backticked path that does not exist in the repo
  SPEC-OPEN     an open `- [ ] T<n>` task in specs/*/tasks.md whose spec folder has a later `- [x]` with a merge SHA (possibly
                abandoned); a weak signal, listed for the human
Exit 0 always (a report, not a gate). Stdlib only; `gh` is optional (--no-gh skips NOTE-CLOSED lookups).
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

NOTE = re.compile(r"\b(TODO|FIXME|XXX|HACK)\b[:(]?(.*)")
ISSUE = re.compile(r"(?:github\.com/([\w.-]+/[\w.-]+)/issues/(\d+))|(?<![\w/])#(\d{1,6})\b")
PATHLIKE = re.compile(r"`([A-Za-z0-9_.@-]+(?:/[A-Za-z0-9_.@*-]+)+(?:\.[A-Za-z0-9]+)?)`")
SKIP_DIRS = {".git", "node_modules", "vendor", ".venv", "venv", "dist", "build", "__pycache__", ".next", "storage",
             "ai-knowledge-base", "runs", ".factory-worktrees"}
CODE_EXT = {".py", ".php", ".ts", ".tsx", ".js", ".jsx", ".sh", ".go", ".rs", ".dart", ".swift", ".kt", ".rb",
            ".vue", ".blade.php", ".java", ".cs"}
MAX_NOTES = 400
OLD_DAYS = 365


def run(argv, cwd=None, timeout=60) -> tuple[int, str]:
    try:
        p = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout
    except (OSError, subprocess.TimeoutExpired):
        return 127, ""


def tracked_files(repo: Path) -> list[str]:
    rc, out = run(["git", "ls-files"], cwd=repo)
    files = out.splitlines() if rc == 0 else []
    return [f for f in files if not (set(Path(f).parts) & SKIP_DIRS)]


def repo_slug(repo: Path) -> str | None:
    rc, out = run(["git", "remote", "-v"], cwd=repo)
    m = re.search(r"github\.com[:/]([\w.-]+/[\w.-]+?)(?:\.git)?\s", out)
    return m.group(1) if m else None


def issue_state(slug: str, n: str, cache: dict) -> str | None:
    key = f"{slug}#{n}"
    if key not in cache:
        rc, out = run(["gh", "issue", "view", n, "-R", slug, "--json", "state,closedAt"], timeout=30)
        try:
            d = json.loads(out) if rc == 0 else None
        except ValueError:
            d = None
        cache[key] = f"{d['state']} {d.get('closedAt') or ''}".strip() if d else None
    return cache[key]


def blame_epoch(repo: Path, f: str, line: int) -> int | None:
    rc, out = run(["git", "blame", "--porcelain", "-L", f"{line},{line}", "--", f], cwd=repo, timeout=30)
    m = re.search(r"^committer-time (\d+)$", out, re.M)
    return int(m.group(1)) if rc == 0 and m else None


def notes(repo: Path, files: list[str], use_gh: bool) -> list[str]:
    out, cache, seen = [], {}, 0
    slug = repo_slug(repo) if use_gh else None
    now = time.time()
    for f in files:
        if not any(f.endswith(e) for e in CODE_EXT):
            continue
        try:
            lines = (repo / f).read_text(errors="replace").splitlines()
        except OSError:
            continue
        for i, text in enumerate(lines, 1):
            m = NOTE.search(text)
            if not m:
                continue
            seen += 1
            if seen > MAX_NOTES:
                out.append(f"NOTE-LIMIT    stopped after {MAX_NOTES} notes; run on a subfolder for the rest")
                return out
            refs = list(ISSUE.finditer(text))
            if refs:
                for r in refs:
                    s, n = (r.group(1), r.group(2)) if r.group(1) else (slug, r.group(3))
                    st = issue_state(s, n, cache) if (use_gh and s) else None
                    if st and st.startswith("CLOSED"):
                        out.append(f"NOTE-CLOSED   {f}:{i}  {s}#{n} is {st}  |  {text.strip()[:140]}")
                continue
            t = blame_epoch(repo, f, i)
            if t and now - t > OLD_DAYS * 86400:
                out.append(f"NOTE-OLD      {f}:{i}  untouched {int((now - t) / 86400)} days  |  {text.strip()[:140]}")
    return out


def path_exists(repo: Path, p: str, files: set[str]) -> bool:
    p = p.strip("/").removeprefix("./")
    if "*" in p:
        return any(Path(f).match(p) for f in files)
    return (repo / p).exists() or any(f.startswith(p + "/") for f in files)


def doc_paths(repo: Path, files: set[str]) -> list[str]:
    docs = [d for d in ("CLAUDE.md", "AGENTS.md", "README.md") if (repo / d).exists()]
    docs += sorted(str(p.relative_to(repo)) for p in (repo / "docs").glob("*.md")) if (repo / "docs").is_dir() else []
    return _paths_in(repo, docs, files, "DOC-PATH ", repo)


def memory_paths(repo: Path, mem: Path, files: set[str]) -> list[str]:
    if not mem.is_dir():
        return [f"MEMORY-SKIP   {mem} is not a directory"]
    return _paths_in(mem, sorted(p.name for p in mem.glob("*.md")), files, "MEMORY-PATH", repo)


def _paths_in(base: Path, names: list[str], files: set[str], tag: str, repo: Path) -> list[str]:
    out = []
    first_dirs = {Path(f).parts[0] for f in files}
    for d in names:
        try:
            lines = (base / d).read_text(errors="replace").splitlines()
        except OSError:
            continue
        for i, text in enumerate(lines, 1):
            for m in PATHLIKE.finditer(text):
                p = m.group(1)
                if p.startswith(("~", "http", "/")) or "@" in p.split("/")[0] or re.search(r"NNN|XXX|YYYY", p):
                    continue
                if Path(p).parts[0] not in first_dirs:      # only paths that claim to be inside this repo
                    continue
                if not path_exists(repo, p, files):
                    out.append(f"{tag}   {d}:{i}  `{p}` does not exist  |  {text.strip()[:140]}")
    return out


def spec_open(repo: Path) -> list[str]:
    out = []
    for t in sorted((repo / "specs").glob("*/tasks.md")) if (repo / "specs").is_dir() else []:
        lines = t.read_text(errors="replace").splitlines()
        done = [i for i, ln in enumerate(lines) if re.match(r"\s*- \[x\].*\b[0-9a-f]{7,40}\b", ln)]
        for i, ln in enumerate(lines):
            if re.match(r"\s*- \[ \] T\d", ln) and done and max(done) > i:   # T-tasks only, not follow-ups
                out.append(f"SPEC-OPEN     {t.relative_to(repo)}:{i + 1}  open, but later tasks are merged  |  {ln.strip()[:140]}")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("repo")
    ap.add_argument("--memory", help="memory folder to check (for example ~/.claude/projects/<slug>/memory)")
    ap.add_argument("--no-gh", action="store_true", help="skip closed-issue lookups")
    a = ap.parse_args(argv)
    repo = Path(a.repo).expanduser().resolve()
    files = tracked_files(repo)
    fset = set(files)
    rows = notes(repo, files, not a.no_gh) + doc_paths(repo, fset) + spec_open(repo)
    if a.memory:
        rows += memory_paths(repo, Path(a.memory).expanduser(), fset)
    print(f"# sweep candidates: {repo} ({len(files)} tracked files)\n")
    print("Claims only. Each needs the verifier pass before anyone acts on it; nothing was changed.\n")
    for r in rows:
        print(f"- {r}")
    if not rows:
        print("- none")
    print(f"\ncount: {len(rows)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
