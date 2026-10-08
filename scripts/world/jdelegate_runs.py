"""world/jdelegate_runs.py — parse ~/.cache/jdelegate/<ISO>-<label>-* dirs.

One event per run. status: done (exit=0), failed (exit!=0), running (no exit file).
Model + label from line 2 of run.sh '# jdelegate worker: <label> · <model>' else -m flag.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from lib_world import SRC_JDELEGATE, event, make_id, slug

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
        try:
            label, model = parse_run_sh(run_sh.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            label, model = "", ""
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
        yield event(
            id=make_id(SRC_JDELEGATE, child.name),
            ts=ts, project="jdelegate",
            kind="worker", status=status, title=title,
            ref="", url="", actor="jdelegate", model=model,
            dur_s=dur if dur else None,
            source=SRC_JDELEGATE,
        )
