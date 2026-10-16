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
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

from lib_world import (
    HOST, SRC_GIT, SRC_HERDR, SRC_JDELEGATE, SRC_KB, SRC_PR, SRC_SKILLS,
    SRC_SPEC, SRC_SWOT, SRC_TASKS, SRC_TRANSCRIPTS, SRC_TRACK, VALID_KINDS,
    VALID_STATUSES, canonical_project, event, iter_git_roots,
    looks_like_worktree, make_id, project_from_transcript_folder, slug,
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

def _is_git_worktree(dirpath: Path) -> bool:
    """True when `dirpath` is a git worktree (not the main checkout).

    Implementation: a worktree has `--git-common-dir` pointing to a path
    whose resolved location is OUTSIDE the current dirpath, while its
    `--git-dir` resolves INTO dirpath. (The main checkout has both equal.)
    """
    try:
        cp = subprocess.run(
            ["git", "-C", str(dirpath), "rev-parse",
             "--path-format=absolute",
             "--git-common-dir", "--git-dir"],
            capture_output=True, text=True, timeout=5,
        )
    except Exception:
        return False
    if cp.returncode != 0:
        return False
    lines = cp.stdout.strip().splitlines()
    if len(lines) < 2:
        return False
    common = lines[0].strip()
    gitd = lines[1].strip()
    if not common or not gitd:
        return False
    try:
        return Path(common).resolve() != Path(gitd).resolve()
    except Exception:
        return False


def collect_session_tasks() -> Iterable[dict]:
    cutoff = _cutoff()
    out: list[dict] = []
    for base in _SESSION_GLOBS:
        if not base.exists():
            continue
        for p in sorted(base.glob("*/specs/_session/*-tasks.md")):
            if "/.worktrees/" in str(p) or "/.claude/worktrees/" in str(p):
                continue
            if looks_like_worktree(p):
                continue
            # Canonicalise via git-common-dir so worktrees / feature copies
            # collapse to the base repo (FashionVerse-g-pricing -> fashionverse).
            try:
                parent_parts = list(p.relative_to(base).parts)
            except ValueError:
                parent_parts = p.parts
            repo_dir = base / parent_parts[0] if parent_parts else p
            # Skip worktree copies: only scan files inside the main checkout of
            # a logical repo. A git worktree of FashionVerse (e.g.
            # FashionVerse-g-pricing) has --git-common-dir pointing back to the
            # main checkout's .git.
            if _is_git_worktree(repo_dir):
                continue
            project_slug = canonical_project(repo_dir)
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
    if not base.exists():
        return
    # Scan one level of repos: <base>/<repo>/specs/<NNN-...>/tasks.md.
    # Skip worktree copies and the session-logs dir under each repo.
    for repo_dir in sorted(base.iterdir()):
        if not repo_dir.is_dir():
            continue
        if looks_like_worktree(repo_dir):
            continue
        if _is_git_worktree(repo_dir):
            continue
        spec_dir = repo_dir / "specs"
        if not spec_dir.exists():
            continue
        for p in sorted(spec_dir.glob("*/tasks.md")):
            if looks_like_worktree(p):
                continue
            if _is_git_worktree(p.parent.parent):
                continue
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
            repo_dir = base / parent_parts[0] if parent_parts else spec_path
            project_slug = canonical_project(repo_dir)
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

STATE_DIR = Path(os.environ.get("WORLD_STATE_DIR", str(Path.home() / ".local/state/world")))
_PENDING_STATE: dict[Path, str] = {}


def _state_read(p: Path) -> str:
    try:
        return p.read_text().strip()
    except Exception:
        return ""


def commit_state() -> None:
    """Persist per-repo last-seen shas; call after a successful send."""
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        for p, v in _PENDING_STATE.items():
            p.write_text(v + "\n")
    except Exception:
        pass
    _PENDING_STATE.clear()


def _git_out(repo: Path, args: list[str], timeout: int = 20) -> str | None:
    try:
        cp = subprocess.run(["git", "-C", str(repo), *args],
                            capture_output=True, text=True, timeout=timeout)
    except Exception:
        return None
    return cp.stdout if cp.returncode == 0 else None


def _git_log(repo: Path, since: str, rev: str = "") -> list[tuple[str, str, str]]:
    """Return [(short_sha, committer_iso, subject)]; rev like 'abc..HEAD' or ''."""
    args = ["log", "--pretty=format:%h %cI", "-n", "5000"]
    args += [rev] if rev else [f"--since={since}"]
    out_s = _git_out(repo, args)
    if out_s is None:
        return []
    out: list[tuple[str, str, str]] = []
    for ln in out_s.splitlines():
        parts = ln.strip().split(" ", 2)
        if len(parts) >= 2:
            out.append((parts[0], parts[1], parts[2] if len(parts) > 2 else ""))
    return out


def _resolve_canonical_repo(repo: Path) -> tuple[Path, str] | None:
    """Return (canonical_repo_dir, project_slug) for a discovered git root.

    The canonical repo directory is the main worktree (parent of the resolved
    `--git-common-dir`). That is the single source of truth for one logical
    repository: every worktree of the same repo shares --git-common-dir and we
    only want to scan commits ONCE.
    """
    try:
        cp = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "--path-format=absolute",
             "--git-common-dir"],
            capture_output=True, text=True, timeout=5,
        )
    except Exception:
        return None
    if cp.returncode != 0 or not cp.stdout.strip():
        return None
    common = Path(cp.stdout.strip())
    if common.name != ".git":
        return None
    canonical_dir = common.parent
    if not canonical_dir.exists():
        return None
    return canonical_dir, slug(canonical_dir.name)


def collect_git(roots: list[Path] | None = None) -> Iterable[dict]:
    cutoff = _cutoff().strftime("%Y-%m-%d")
    if roots is None:
        scan_roots = [Path.home() / "projects", Path.home() / "code"]
    else:
        scan_roots = list(roots)
    out: list[dict] = []
    # Map canonical (real path of the main worktree) -> list of discovered roots.
    by_canonical: dict[str, dict] = {}
    for repo in iter_git_roots([str(r) for r in scan_roots]):
        resolved = _resolve_canonical_repo(repo)
        if not resolved:
            continue
        canonical_dir, project = resolved
        key = str(canonical_dir.resolve())
        bucket = by_canonical.setdefault(
            key, {"canonical": canonical_dir, "project": project,
                  "roots": []},
        )
        bucket["roots"].append(repo)
    for bucket in by_canonical.values():
        canonical_dir: Path = bucket["canonical"]
        project: str = bucket["project"]
        sf = STATE_DIR / f"git.{project}.sha"
        head = (_git_out(canonical_dir, ["rev-parse", "HEAD"], 5) or "").strip()
        if not head:
            continue
        last = _state_read(sf)
        if last == head:
            continue
        commits = _git_log(canonical_dir, cutoff, f"{last}..HEAD") if last else []
        if not commits:
            commits = _git_log(canonical_dir, cutoff)
        _PENDING_STATE[sf] = head
        for sha, ts, subject in commits:
            ts = ts or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            out.append(event(
                id=make_id(SRC_GIT, f"{project}:{sha}"),
                ts=ts, project=project, kind="commit", status="done",
                title=f"commit {sha}", ref=sha, url="", actor="owner",
                source=SRC_GIT,
            ))
    return out


# --- PRs (gh) ---------------------------------------------------------------

def collect_prs() -> Iterable[dict]:
    pf = STATE_DIR / "gh-prs.ts"
    try:
        if time.time() - float(_state_read(pf) or 0) < 3600:
            return []
    except Exception:
        pass
    def _run(query_flag: str) -> list[dict]:
        try:
            cp = subprocess.run(
                ["gh", "search", "prs", query_flag, "@me", "--limit", "1000",
                 "--json", "number,title,state,repository,url,createdAt,closedAt"],
                capture_output=True, text=True, timeout=60,
            )
        except Exception:
            return []
        if cp.returncode != 0 or not cp.stdout.strip():
            return []
        try:
            return json.loads(cp.stdout)
        except Exception:
            return []
    seen: set[tuple[str, str]] = set()  # (repo, number)
    out: list[dict] = []
    # Author first, then reviewed-by. The server dedupes by id; we also
    # dedupe locally so a PR that is BOTH authored and reviewed doesn't get
    # two events.
    for pr in _run("--author") + _run("--reviewed-by"):
        repo = (pr.get("repository") or {}).get("nameWithOwner") or "unknown/unknown"
        num = pr.get("number")
        if num is None:
            continue
        key = (repo, str(num))
        if key in seen:
            continue
        seen.add(key)
        state = (pr.get("state") or "").lower()
        # The repo name on `gh search prs` can be a worktree-style feature copy
        # (e.g. "FashionVerse-g-pricing"). Canonicalise the project via git so
        # such PRs collapse back to "fashionverse".
        repo_short = repo.split("/", 1)[1] if "/" in repo else repo
        canonical_dir = Path.home() / "projects" / repo_short
        if canonical_dir.exists():
            proj = canonical_project(canonical_dir)
        else:
            proj = slug(repo_short)
        title = f"PR #{num}"
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
            id=make_id(SRC_PR, f"{repo}#{num}"),
            ts=ts, project=proj, kind=kind, status=status,
            title=title, ref=str(num),
            url=pr.get("url") or "", actor="owner",
            source=SRC_PR,
        ))
    if out:
        _PENDING_STATE[pf] = str(int(time.time()))
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


# --- skill USE (transcripts) ------------------------------------------------
# Scans ~/.claude/projects/**/*.jsonl for tool_use blocks with name 'Skill',
# reads ONLY input.skill, and emits one kind=skill event per (skill, project, day)
# with a "<skill> used Nx" title. Stream-friendly: never reads content as a
# whole, never stores transcript text, first run limited to files modified
# in the last 90 days.

SRC_SKILL_USE = "skill-use"
_SKILL_TOOL_RE = re.compile(r'"name"\s*:\s*"Skill"')
_SKILL_FIELD_RE = re.compile(r'"skill"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)"')

def _scan_file_for_skill_use(path: Path) -> list[tuple[str, str]]:
    """Return [(skill, day)] pairs found in `path` by streaming line-by-line.

    The file may be up to ~12 GB; we never load it whole. We skip lines that
    don't contain the literal 'Skill' string (the tool name) so the cost of
    the scan is roughly proportional to the number of tool_use blocks, not
    the size of the file.
    """
    out: list[tuple[str, str]] = []
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            for ln in fh:
                if '"Skill"' not in ln:
                    continue
                # Cheap filter: only lines with the tool_use shape are interesting.
                if not _SKILL_TOOL_RE.search(ln):
                    continue
                m = _SKILL_FIELD_RE.search(ln)
                if not m:
                    continue
                skill = m.group(1)
                # Day is taken from the file's mtime — the file's mtime matches
                # the most recent activity in it, which is the most actionable
                # day for the skill-use signal. The id uses the same day.
                try:
                    mt = path.stat().st_mtime
                except Exception:
                    continue
                day = datetime.fromtimestamp(mt, tz=timezone.utc).strftime("%Y-%m-%d")
                out.append((skill, day))
    except (OSError, UnicodeDecodeError):
        return out
    return out


def collect_skill_use() -> Iterable[dict]:
    """Emit one event per (skill, project, day) tuple found in transcripts.

    - Streams line-by-line; never holds the file in memory.
    - Skips lines that don't contain the literal '"Skill"' before doing any work.
    - First run: only files modified in the last 90 days. Later runs resume
      from a per-file (size, offset) cursor in ~/.local/state/world/skill-scan.json.
    - Reads ONLY `input.skill` from each matched tool_use block.
    """
    root = Path.home() / ".claude" / "projects"
    if not root.exists():
        return []
    cursor_path = STATE_DIR / "skill-scan.json"
    try:
        cursor = json.loads(cursor_path.read_text()) if cursor_path.exists() else {}
    except Exception:
        cursor = {}
    if not isinstance(cursor, dict):
        cursor = {}
    # tracks last-seen (size, mtime) per file path (str).
    files: dict[str, dict] = cursor.get("files", {}) or {}
    # Cumulative "skill|proj|day" -> count across runs, so each event reports the
    # day's total rather than this run's delta.
    totals: dict[str, int] = cursor.get("totals", {}) or {}
    cutoff_ts = (datetime.now(timezone.utc) - timedelta(days=90)).timestamp()

    # Counters keyed by (skill, project, day). The day comes from the file's
    # mtime at scan time.
    counts: dict[tuple[str, str, str], int] = {}
    affected_files: set[str] = set()

    jsonl_paths: list[Path] = []
    for dirpath, _dirs, filenames in os.walk(root):
        for fn in filenames:
            if not fn.endswith(".jsonl"):
                continue
            p = Path(dirpath) / fn
            jsonl_paths.append(p)

    for p in jsonl_paths:
        spath = str(p)
        # Fast path: if the cursor already records this file at exactly the
        # same mtime, we can trust the previous scan and skip stat() entirely.
        # macOS stat() on a cold cache over thousands of files is the dominant
        # cost on the second run.
        prev_quick = files.get(spath)
        if prev_quick and isinstance(prev_quick, dict):
            try:
                if abs(float(prev_quick.get("mtime", 0.0)) - p.stat().st_mtime) < 1e-3:
                    continue
            except OSError:
                pass
        try:
            st = p.stat()
        except OSError:
            continue
        size = st.st_size
        mtime = st.st_mtime
        prev = files.get(spath) or {}
        prev_size = int(prev.get("size", 0)) if isinstance(prev, dict) else 0
        prev_mtime = float(prev.get("mtime", 0.0)) if isinstance(prev, dict) else 0.0
        # 90-day window: if the file is outside it AND we have no record of
        # it (or its record also shows it's stale), skip it. We never want
        # the skills guild to read a 12 GB transcript that's been quiet for
        # months. Files we already tracked are also skipped once their
        # mtime is stale: re-scanning a stale file is wasted work.
        is_stale = mtime < cutoff_ts
        if is_stale and (not prev or prev_mtime < cutoff_ts):
            files[spath] = {"size": size, "mtime": mtime}
            continue
        # If the file shrank (rotated/truncated), re-read from the start.
        start = 0 if size < prev_size else prev_size
        # If the mtime went backwards, the file was rewritten — re-read.
        if mtime + 1e-3 < prev_mtime:
            start = 0
        # Project from the parent folder name (no transcript content needed).
        proj = project_from_transcript_folder(p.parent.name)
        if start == 0:
            pairs = _scan_file_for_skill_use(p)
        else:
            # Only read the appended tail. Skip if the appended region is empty.
            if size == start:
                pairs = []
            else:
                pairs = []
                try:
                    with p.open("rb") as fh:
                        fh.seek(start)
                        for raw in fh:
                            try:
                                ln = raw.decode("utf-8", errors="replace")
                            except Exception:
                                continue
                            if '"Skill"' not in ln:
                                continue
                            if not _SKILL_TOOL_RE.search(ln):
                                continue
                            m = _SKILL_FIELD_RE.search(ln)
                            if not m:
                                continue
                            skill = m.group(1)
                            day = datetime.fromtimestamp(mtime, tz=timezone.utc).strftime("%Y-%m-%d")
                            pairs.append((skill, day))
                except OSError:
                    pairs = []
        if pairs:
            affected_files.add(spath)
        for skill, day in pairs:
            counts[(skill, proj, day)] = counts.get((skill, proj, day), 0) + 1
        files[spath] = {"size": size, "mtime": mtime}

    touched: dict[str, tuple[str, str, str]] = {}
    for (skill, proj, day), n in counts.items():
        key = f"{skill}|{proj}|{day}"
        totals[key] = totals.get(key, 0) + n
        touched[key] = (skill, proj, day)

    # Cursor is committed by commit_state() only after a successful send, so a
    # failed run re-scans the same delta instead of losing it.
    _PENDING_STATE[cursor_path] = json.dumps({"files": files, "totals": totals})

    out: list[dict] = []
    for key, (skill, proj, day) in sorted(touched.items()):
        n = totals[key]
        out.append(event(
            # The total is part of the id so a later, larger total is a new event.
            id=make_id(SRC_SKILL_USE, f"{skill}:{proj}:{day}:{n}"),
            ts=f"{day}T00:00:00Z",
            project=proj, kind="skill", status="done",
            title=f"{skill} used {n}x", ref="", url="",
            actor="owner", model="", source=SRC_SKILL_USE,
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
        title = "worker"  # pane titles can carry message text; never send them
        cwd = p.get("cwd") or ""
        status = "running"
        # Canonicalise the cwd against git so workers in a worktree / feature
        # copy collapse to the base repo (e.g. FashionVerse-g-pricing ->
        # fashionverse). Falls back to slug(cwd.name) for non-git dirs.
        if cwd:
            proj = canonical_project(cwd)
            if proj == "unknown":
                proj = slug(Path(cwd).name)
        else:
            proj = "herdr"
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
        return []
    buckets: dict[tuple[str, str], int] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        proj = None
        for fn in filenames:
            if not fn.endswith(".jsonl"):
                continue
            try:
                mt = os.stat(os.path.join(dirpath, fn)).st_mtime
            except Exception:
                continue
            if proj is None:
                # Project slug comes from the folder name itself (no transcript
                # content is read), canonicalised to map worktree-derived
                # folders back to the base repo.
                proj = project_from_transcript_folder(os.path.basename(dirpath))
            day = datetime.fromtimestamp(mt, tz=timezone.utc).strftime("%Y-%m-%d")
            buckets[(proj, day)] = buckets.get((proj, day), 0) + 1
    for (proj, day), n in sorted(buckets.items()):
        out.append(event(
            id=make_id(SRC_TRANSCRIPTS, f"{proj}:{day}"),
            ts=f"{day}T00:00:00Z",
            project=proj, kind="status", status="up",
            title=f"{proj} {n} transcript files", ref="", url="",
            actor="owner", model="", source=SRC_TRANSCRIPTS,
        ))
    return out


# --- heartbeat per source ---------------------------------------------------

SOURCES = [
    SRC_TASKS, SRC_SPEC, SRC_JDELEGATE, SRC_GIT, SRC_PR,
    SRC_SKILLS, SRC_SKILL_USE, SRC_SWOT, SRC_KB, SRC_HERDR, SRC_TRANSCRIPTS,
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
