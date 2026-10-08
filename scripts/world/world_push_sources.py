"""world-push collectors.

One module per source family, plus a coordinator that calls them, dedupes
against the local sent-id cache, and hands the events to the shared sender.

Pure functions where possible; filesystem reads are scoped to the contract:
no message text, no file contents (counts and metadata only).
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

from lib_world import (
    HOST, SRC_GIT, SRC_HERDR, SRC_JDELEGATE, SRC_KB, SRC_PR, SRC_SKILLS,
    SRC_SPEC, SRC_SWOT, SRC_TASKS, SRC_TRANSCRIPTS, SRC_TRACK, VALID_KINDS,
    VALID_STATUSES, event, iter_git_roots, looks_like_worktree, make_id, slug,
)
from task_lines import parse_session_tasks, parse_spec_tasks
from jdelegate_runs import iter_runs

BACKFILL_DAYS = int(os.environ.get("WORLD_BACKFILL_DAYS", "90"))


def _cutoff() -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=BACKFILL_DAYS)


# --- session tasks ----------------------------------------------------------

_SESSION_GLOBS = [
    Path.home() / "projects",
    Path.home() / "code",
]

def collect_session_tasks() -> Iterable[dict]:
    cutoff = _cutoff()
    out: list[dict] = []
    for base in _SESSION_GLOBS:
        if not base.exists():
            continue
        for p in base.rglob("*-tasks.md"):
            if "/.worktrees/" in str(p) or "/.claude/worktrees/" in str(p):
                continue
            if not str(p).endswith("-tasks.md") or "/specs/_session/" not in str(p):
                continue
            if looks_like_worktree(p):
                continue
            # id path: include a stable project slug.
            try:
                parent_parts = list(p.relative_to(base).parts)
            except ValueError:
                parent_parts = p.parts
            project_slug = parent_parts[0] if parent_parts else "unknown"
            try:
                mtime = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc)
            except Exception:
                mtime = datetime.now(timezone.utc)
            if mtime < cutoff and mtime < cutoff:
                # Even if stale, still emit so the historical view is preserved once.
                pass
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            for ev in parse_session_tasks(p, text, project_slug):
                out.append(ev)
    return out


# --- spec-kit --------------------------------------------------------------

def _spec_root(base: Path) -> Iterable[Path]:
    spec_dir = base / "specs"
    if not spec_dir.exists():
        return
    for p in spec_dir.glob("*/tasks.md"):
        if "/.worktrees/" in str(p) or looks_like_worktree(p):
            continue
        # Spec dirs may include session logs already collected; skip those.
        parts = p.parts
        if "_session" in parts:
            continue
        yield p

def collect_specs() -> Iterable[dict]:
    out: list[dict] = []
    seen_ids: set[str] = set()
    for base in _SESSION_GLOBS:
        if not base.exists():
            continue
        for spec_path in _spec_root(base):
            try:
                parent_parts = list(spec_path.relative_to(base).parts)
            except ValueError:
                parent_parts = spec_path.parts
            project_slug = parent_parts[0] if parent_parts else "unknown"
            try:
                text = spec_path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            for ev in parse_spec_tasks(spec_path, text, project_slug):
                # One heartbeat per spec per source path; collector dedupes later.
                out.append(ev)
                seen_ids.add(ev["id"])
    return out


# --- jdelegate --------------------------------------------------------------

JDELEGATE_ROOT = Path.home() / ".cache/jdelegate"

def collect_jdelegate() -> Iterable[dict]:
    return list(iter_runs(JDELEGATE_ROOT))


# --- git commits ------------------------------------------------------------

def _git_log(repo: Path, since: str) -> list[tuple[str, str]]:
    """Return [(short_sha, subject)] from `git log` since `since` (ISO date)."""
    try:
        cp = subprocess.run(
            ["git", "-C", str(repo), "log", f"--since={since}",
             "--pretty=format:%h %s", "-n", "5000"],
            capture_output=True, text=True, timeout=20,
        )
    except Exception:
        return []
    if cp.returncode != 0:
        return []
    out: list[tuple[str, str]] = []
    for ln in cp.stdout.splitlines():
        ln = ln.strip()
        if not ln:
            continue
        sha, _, rest = ln.partition(" ")
        out.append((sha, rest))
    return out

def _git_committer_date(repo: Path, sha: str) -> str | None:
    try:
        cp = subprocess.run(
            ["git", "-C", str(repo), "show", "-s", "--format=%cI", sha],
            capture_output=True, text=True, timeout=5,
        )
    except Exception:
        return None
    if cp.returncode != 0:
        return None
    return cp.stdout.strip() or None

def collect_git() -> Iterable[dict]:
    cutoff = _cutoff().strftime("%Y-%m-%d")
    out: list[dict] = []
    for repo in iter_git_roots([str(Path.home() / "projects"),
                                 str(Path.home() / "code")]):
        project = slug(repo.name)
        for sha, subject in _git_log(repo, cutoff):
            ts = _git_committer_date(repo, sha) or ""
            if not ts:
                ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            out.append(event(
                id=make_id(SRC_GIT, f"{repo}:{sha}"),
                ts=ts, project=project, kind="commit", status="done",
                title=subject, ref=sha, url="", actor="owner",
                source=SRC_GIT,
            ))
    return out


# --- PRs (gh) ---------------------------------------------------------------

def collect_prs() -> Iterable[dict]:
    try:
        cp = subprocess.run(
            ["gh", "search", "prs", "--author", "@me", "--limit", "200",
             "--json", "number,title,state,repository,url,createdAt,closedAt"],
            capture_output=True, text=True, timeout=30,
        )
    except Exception:
        return []
    if cp.returncode != 0 or not cp.stdout.strip():
        return []
    try:
        data = json.loads(cp.stdout)
    except Exception:
        return []
    out: list[dict] = []
    for pr in data:
        state = (pr.get("state") or "").lower()
        repo = (pr.get("repository") or {}).get("nameWithOwner") or "unknown/unknown"
        proj = slug(repo.split("/", 1)[1] if "/" in repo else repo)
        title = pr.get("title") or f"PR #{pr.get('number')}"
        ts = pr.get("createdAt") or pr.get("closedAt") or ""
        if state == "merged":
            kind, status = "merge", "done"
        elif state == "open":
            kind, status = "pr", "pending"
        elif state == "closed":
            kind, status = "pr", "failed"
        else:
            kind, status = "pr", "pending"
        out.append(event(
            id=make_id(SRC_PR, f"{repo}#{pr.get('number')}"),
            ts=ts, project=proj, kind=kind, status=status,
            title=title, ref=str(pr.get("number") or ""),
            url=pr.get("url") or "", actor="owner",
            source=SRC_PR,
        ))
    return out


# --- skills -----------------------------------------------------------------

SKILL_LOCATIONS = [
    Path.home() / ".claude" / "skills",
    Path.home() / ".claude" / "skills-parked",
    Path("~/code/dev-stack/skills").expanduser(),
]

def collect_skills() -> Iterable[dict]:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out: list[dict] = []
    for root in SKILL_LOCATIONS:
        if not root.exists():
            continue
        for child in sorted(root.iterdir()):
            if not child.is_dir():
                continue
            name = child.name
            if name.startswith("."):
                continue
            status = "installed" if "skills-parked" not in str(root) else "parked"
            out.append(event(
                id=make_id(SRC_SKILLS, f"{root}:{name}:{today}"),
                ts=f"{today}T00:00:00Z",
                project="skills", kind="skill", status="done",
                title=f"{name} {status}", ref="", url="",
                actor="owner", model="", source=SRC_SKILLS,
            ))
    return out


# --- market-swot ------------------------------------------------------------

SWOT_ROOTS = [Path.home() / "projects", Path.home() / "code"]

def collect_swot() -> Iterable[dict]:
    out: list[dict] = []
    for base in SWOT_ROOTS:
        if not base.exists():
            continue
        for swot in base.glob("*/docs/brand-swot/*/"):
            if "/.worktrees/" in str(swot) or looks_like_worktree(swot):
                continue
            project = slug(swot.parts[-4])
            d = swot.name.rstrip("/") or swot.parents[0].name
            out.append(event(
                id=make_id(SRC_SWOT, str(swot)),
                ts=f"{d}T00:00:00Z" if re.match(r"\d{4}-\d{2}-\d{2}$", d) else datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                project=project, kind="swot", status="done",
                title=f"market-swot {d}", ref="", url="",
                actor="owner", model="", source=SRC_SWOT,
            ))
    return out


# --- KB counts --------------------------------------------------------------

KB_SUBS = ("concepts", "sources", "qa")

def collect_kb() -> Iterable[dict]:
    out: list[dict] = []
    for base in SWOT_ROOTS:
        if not base.exists():
            continue
        for kb_root in base.glob("*/ai-knowledge-base/knowledge"):
            if looks_like_worktree(kb_root):
                continue
            project = slug(kb_root.parts[-3])
            counts = {}
            for sub in KB_SUBS:
                p = kb_root / sub
                if p.exists():
                    counts[sub] = sum(1 for _ in p.rglob("*") if _.is_file())
                else:
                    counts[sub] = 0
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            title = f"kb c={counts['concepts']} s={counts['sources']} q={counts['qa']}"
            out.append(event(
                id=make_id(SRC_KB, f"{kb_root}:{today}"),
                ts=f"{today}T00:00:00Z",
                project=project, kind="kb", status="up",
                title=title, ref="", url="", actor="owner", model="",
                source=SRC_KB,
            ))
    return out


# --- herdr ------------------------------------------------------------------

def collect_herdr() -> Iterable[dict]:
    if shutil.which("herdr") is None:
        return []
    try:
        cp = subprocess.run(
            ["herdr", "pane", "list"],
            capture_output=True, text=True, timeout=10,
        )
    except Exception:
        return []
    if cp.returncode != 0:
        return []
    try:
        data = json.loads(cp.stdout)
    except Exception:
        return []
    panes = (data.get("result") or {}).get("panes") or []
    out: list[dict] = []
    for p in panes:
        title = (p.get("terminal_title_stripped") or p.get("title") or "").strip() or "worker"
        cwd = p.get("cwd") or ""
        status = "running"
        proj = slug(Path(cwd).name) if cwd else "herdr"
        # Worker pane = has a foreground_cwd of a real project.
        agent = p.get("agent") or "claude"
        out.append(event(
            id=make_id(SRC_HERDR, f"{p.get('pane_id') or ''}",
                       ),
            ts=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            project=proj, kind="worker", status=status,
            title=title, ref=p.get("pane_id") or "", url="",
            actor=agent, model="", source=SRC_HERDR,
        ))
    return out


# --- transcripts (counts only by mtime) -------------------------------------

def collect_transcripts() -> Iterable[dict]:
    root = Path.home() / ".claude" / "projects"
    out: list[dict] = []
    if not root.exists():
        return
    buckets: dict[tuple[str, str], int] = {}
    for p in root.rglob("*.jsonl"):
        try:
            mtime = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc)
        except Exception:
            continue
        day = mtime.strftime("%Y-%m-%d")
        # project = immediate child dir name; stripping leading dashes that come from -encoded paths.
        proj = slug(p.parts[-2] if len(p.parts) >= 2 else "unknown")
        buckets[(proj, day)] = buckets.get((proj, day), 0) + 1
    for (proj, day), n in sorted(buckets.items()):
        out.append(event(
            id=make_id(SRC_TRANSCRIPTS, f"{proj}:{day}"),
            ts=f"{day}T00:00:00Z",
            project="claude-sessions", kind="status", status="up",
            title=f"{proj} {n} transcript files", ref="", url="",
            actor="owner", model="", source=SRC_TRANSCRIPTS,
        ))
    return out


# --- heartbeat per source ---------------------------------------------------

SOURCES = [
    SRC_TASKS, SRC_SPEC, SRC_JDELEGATE, SRC_GIT, SRC_PR,
    SRC_SKILLS, SRC_SWOT, SRC_KB, SRC_HERDR, SRC_TRANSCRIPTS,
]

def heartbeat_counts(events_by_source: dict[str, list[dict]]) -> list[dict]:
    out = []
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for src in SOURCES:
        n = len(events_by_source.get(src, []))
        out.append(event(
            id=make_id(src, f"heartbeat:{now}"),
            ts=now, project=src, kind="source", status="up",
            title=f"{n} events", ref="", url="", actor="owner",
            model="", source=src,
        ))
    return out
