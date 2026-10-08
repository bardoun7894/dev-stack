"""world/task_lines.py — parsers for session task logs and spec-kit tasks files.

No filesystem side effects here — just take a path + raw text and yield events.
Tests live in test_world.sh.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from lib_world import SRC_TASKS, SRC_SPEC, event, make_id, slug

_DONE_LINE = re.compile(
    r"^- \[x\] (\d{1,2}:\d{2})\s+[—–-]\s+(.+?)\s+✓\s+(\d{1,2}:\d{2})\s*\[(.+?)\]\s*$",
    re.IGNORECASE,
)
_DONE_PLAIN = re.compile(
    r"^- \[x\] (\d{1,2}:\d{2})\s+[—–-]\s+(.+?)\s*$",
    re.IGNORECASE,
)
_PENDING = re.compile(
    r"^- \[ \] (\d{1,2}:\d{2})\s+[—–-]\s+(.+?)\s*$",
    re.IGNORECASE,
)

_DATE_FROM_FNAME = re.compile(r"(\d{4}-\d{2}-\d{2})")

def _ts_from_date_and_time(date_str: str, hhmm: str) -> str:
    """Combine file-date and hh:mm into UTC ISO."""
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except Exception:
        d = datetime.now(timezone.utc)
    try:
        h, m = hhmm.split(":")
        d = d.replace(hour=int(h), minute=int(m), second=0, microsecond=0)
    except Exception:
        pass
    return d.strftime("%Y-%m-%dT%H:%M:%SZ")

def _file_date(path: Path) -> str:
    name = path.name
    m = _DATE_FROM_FNAME.search(name)
    if m:
        return m.group(1)
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).strftime("%Y-%m-%d")
    except Exception:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

def parse_session_tasks(path: Path, text: str, project: str) -> Iterable[dict]:
    """Yield task events from a session task log.

    Done lines must match either `_DONE_LINE` (preferred, with explicit done time)
    or `_DONE_PLAIN` (fallback, ts = file date 00:00Z). Pending lines yield pending.
    """
    fdate = _file_date(path)
    key_path = str(path)
    proj = slug(project)
    for ln_no, raw in enumerate(text.splitlines(), start=1):
        raw = raw.rstrip()
        if not raw.startswith("- ["):
            continue
        m = _DONE_LINE.match(raw)
        if m:
            hhm1, body, hhm2, evidence = m.groups()
            ts = _ts_from_date_and_time(fdate, hhm2)
            title = f"{body} [evidence: {evidence}]"
            yield event(
                id=make_id(SRC_TASKS, f"{key_path}:L{ln_no}"),
                ts=ts, project=proj, kind="task", status="done",
                title=title, ref="", url="", actor="owner", model="",
                source=SRC_TASKS,
            )
            continue
        m = _DONE_PLAIN.match(raw)
        if m:
            hhm, body = m.groups()
            ts = _ts_from_date_and_time(fdate, hhm)
            yield event(
                id=make_id(SRC_TASKS, f"{key_path}:L{ln_no}"),
                ts=ts, project=proj, kind="task", status="done",
                title=body, source=SRC_TASKS,
            )
            continue
        m = _PENDING.match(raw)
        if m:
            hhm, body = m.groups()
            ts = _ts_from_date_and_time(fdate, hhm)
            yield event(
                id=make_id(SRC_TASKS, f"{key_path}:L{ln_no}"),
                ts=ts, project=proj, kind="task", status="pending",
                title=body, source=SRC_TASKS,
            )
            continue

_SPEC_PATH = re.compile(r"/specs/(\d{3}-[^/]+)/tasks\.md$")
_TASKS_DONE = re.compile(r"^- \[x\]", re.IGNORECASE)
_TASKS_PENDING = re.compile(r"^- \[ \]", re.IGNORECASE)

def parse_spec_tasks(path: Path, text: str, project: str) -> Iterable[dict]:
    """One kind=task event per feature, with done/total counts in the title."""
    fdate = _file_date(path)
    done = sum(1 for ln in text.splitlines() if _TASKS_DONE.match(ln))
    pending = sum(1 for ln in text.splitlines() if _TASKS_PENDING.match(ln))
    total = done + pending
    m = _SPEC_PATH.search(str(path))
    fcode = m.group(1) if m else path.stem
    title = f"feature {fcode}: {done}/{total} done"
    proj = slug(project)
    yield event(
        id=make_id(SRC_SPEC, f"{path}:counts"),
        ts=_ts_from_date_and_time(fdate, "00:00"),
        project=proj, kind="task", status="done" if pending == 0 else "pending",
        title=title, source=SRC_SPEC,
    )

_REQUIREMENTS_TXT_BLOCK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
