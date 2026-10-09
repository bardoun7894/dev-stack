"""world/jdelegate_runs.py — parse ~/.cache/jdelegate/<ISO>-<label>-* dirs.

One event per run. status: done (exit=0), failed (exit!=0), running (no exit file; failed if pid dead and run.sh >6h old).
Model + label from line 2 of run.sh '# jdelegate worker: <label> · <model>' else -m flag.
"""
from __future__ import annotations

import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from lib_world import SRC_JDELEGATE, canonical_project, event, make_id, slug

_DIR_RE = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}-\d{3}Z)-(.+)$")

def parse_ts_from_dirname(name: str) -> str | None:
    m = _DIR_RE.match(name)
    if not m:
        return None
    iso_raw, _ = m.groups()
    # YYYY-MM-DDTHH-MM-SS-mmmZ → split into date+time parts.
    date_part, _, time_part = iso_raw.partition("T")
    yyyy, mm, dd = date_part.split("-")
    time_no_z = time_part.rstrip("Z")
    hh, mn, ss, mmm = time_no_z.split("-")
    return f"{yyyy}-{mm}-{dd}T{hh}:{mn}:{ss}.{int(mmm):03d}Z"

_HEADER = re.compile(r"^#\s*jdelegate worker:\s*(.+?)\s*[·•]\s*(.+?)\s*$")
_MODEL_FLAG = re.compile(r"-m\s+['\"]?([^\s'\"]+)")

def parse_run_sh(text: str) -> tuple[str, str]:
    """Return (label, model). Tries the comment header first; falls back to -m flag."""
    label = ""
    model = ""
    for ln in text.splitlines():
        ln = ln.strip()
        m = _HEADER.match(ln)
        if m:
            label = m.group(1).strip()
            model = m.group(2).strip()
            if label and model:
                return label, model
    for ln in text.splitlines():
        m = _MODEL_FLAG.search(ln)
        if m:
            model = m.group(1).strip()
            if not label:
                # Heuristic: any non-shell token on line 2 of file (the comment),
                # or caller's brief.
                pass
    return label, model

_CD_RE = re.compile(r"^cd\s+'([^']+)'\s*\|\|\s*exit\b")
_STALE_S = 6 * 3600

def parse_cd_dir(text: str) -> str | None:
    for ln in text.splitlines():
        m = _CD_RE.match(ln.strip())
        if m:
            return m.group(1)
    return None

def pid_alive(pid_path: Path) -> bool:
    try:
        pid = int(pid_path.read_text().strip())
        if pid <= 0:
            return False
        os.kill(pid, 0)
    except PermissionError:
        return True
    except Exception:
        return False
    return True

def status_from_exit(exit_path: Path) -> tuple[str, float | None]:
    """Return (status, dur_s). dur_s is computed from exit mtime vs run.sh mtime."""
    if not exit_path.exists():
        return "running", None
    try:
        code = int(exit_path.read_text().strip() or "-1")
    except Exception:
        code = -1
    status = "done" if code == 0 else "failed"
    return status, None  # filled in by caller once it has run.sh

def iter_runs(root: Path) -> Iterable[dict]:
    if not root.exists():
        return
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        m = _DIR_RE.match(child.name)
        if not m:
            continue
        ts = parse_ts_from_dirname(child.name)
        if not ts:
            continue
        run_sh = child / "run.sh"
        if not run_sh.exists():
            continue
        cd_dir = None
        try:
            text = run_sh.read_text(encoding="utf-8", errors="replace")
            label, model = parse_run_sh(text)
            cd_dir = parse_cd_dir(text)
        except Exception:
            label, model = "", ""
        project = canonical_project(cd_dir) if cd_dir else "dev-stack"
        exit_path = child / "exit"
        status, _ = status_from_exit(exit_path)
        dur = None
        try:
            if exit_path.exists():
                dur = max(0.0, exit_path.stat().st_mtime - run_sh.stat().st_mtime)
            elif (child / "out.log").exists():
                dur = max(0.0, (child / "out.log").stat().st_mtime - run_sh.stat().st_mtime)
        except Exception:
            dur = None
        title = label or child.name
        if status == "running":
            try:
                old = time.time() - run_sh.stat().st_mtime > _STALE_S
            except Exception:
                old = False
            if old and not pid_alive(child / "pid"):
                status = "failed"
                title += " (no exit)"
        yield event(
            id=make_id(SRC_JDELEGATE, child.name + ":v2"),
            ts=ts, project=project,
            kind="worker", status=status, title=title,
            ref="", url="", actor="jdelegate", model=model,
            dur_s=dur if dur else None,
            source=SRC_JDELEGATE,
        )
