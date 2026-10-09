"""world/lib_world.py — shared helpers for the Mac world producer (world event contract v1).

Single source of truth for IDs, posting, outbox, sent-id cache, and the slug rule.
Portable across bash 3.2 (no f-strings quirks); shipped as a python module so the
two CLI scripts (track + world-push) and the tests share it.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from hashlib import sha1
from pathlib import Path
from typing import Any, Iterable

CONTRACT_VERSION = "v1"

# --- Config ------------------------------------------------------------------

DEFAULT_URL = "http://100.64.0.1:8000/api/godhome/world/event"
STATE_DIR = Path(os.environ.get("WORLD_STATE_DIR", str(Path.home() / ".local/state/world")))
OUTBOX_PATH = STATE_DIR / "outbox.jsonl"
SENT_IDS_PATH = STATE_DIR / "sent.ids"

# Source names. Keep stable — server treats these as collector identifiers.
SRC_TRACK = "track"
SRC_TASKS = "session-tasks"
SRC_SPEC = "spec-kit"
SRC_JDELEGATE = "jdelegate"
SRC_GIT = "git"
SRC_PR = "gh-prs"
SRC_SKILLS = "skills"
SRC_SWOT = "market-swot"
SRC_KB = "kb"
SRC_HERDR = "herdr"
SRC_TRANSCRIPTS = "claude-sessions"

HOST = "mac"

# Allow collectors to override the endpoint via env. Set to an unroutable URL in tests.
def env_url() -> str:
    return os.environ.get("WORLD_URL", DEFAULT_URL)

def env_token() -> str:
    return os.environ.get("WORLD_TOKEN", "")

# --- Slug + id ---------------------------------------------------------------

_SLUG_RE = re.compile(r"[^a-z0-9]+")

def slug(text: str) -> str:
    """Lowercase alphanumeric + dashes. Empty slug -> 'unknown'."""
    if not text:
        return "unknown"
    s = _SLUG_RE.sub("-", text.lower()).strip("-")
    return s or "unknown"

def make_id(source: str, key: str) -> str:
    """sha1('source:key') — same scheme as described in the contract."""
    return sha1(f"{source}:{key}".encode("utf-8")).hexdigest()

def trim_title(s: str, limit: int = 140) -> str:
    s = (s or "").replace("\n", " ").strip()
    return s if len(s) <= limit else s[: limit - 1] + "…"

# Server-side secret filters (src/server/world.ts). Copy exactly so any
# title that would 400 a batch gets neutralised before it leaves the box.
# Flags: only `xox[abprs]-` and `bearer` are case-insensitive on the server.
_SCRUB_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_-]{6,}", re.IGNORECASE),
    re.compile(r"ghp_[A-Za-z0-9]{6,}", re.IGNORECASE),
    re.compile(r"gh[ousr]_[A-Za-z0-9]{6,}", re.IGNORECASE),
    re.compile(r"xox[abprs]- ", re.IGNORECASE),
    re.compile(r"bearer\s+\S+", re.IGNORECASE),
    re.compile(r"[A-Za-z0-9+/=_-]{33,}"),
)

def scrub_title(s: str) -> str:
    """Replace every match of the server secret regexes with '…'.

    Loops because a single replacement can create a new longer alnum run
    that itself qualifies under the 33+ char fallback. Returns the scrubbed
    string unchanged in shape (no truncation) — caller decides the cap.
    """
    if not s:
        return s
    prev = None
    out = s
    while out != prev:
        prev = out
        for pat in _SCRUB_PATTERNS:
            out = pat.sub("…", out)
    return out

# --- JSON helpers ------------------------------------------------------------

def json_dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))

def now_utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

# --- Outbox / sent-id cache --------------------------------------------------

def ensure_state_dir() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)

def outbox_append(events: list[dict]) -> None:
    ensure_state_dir()
    with OUTBOX_PATH.open("a", encoding="utf-8") as fh:
        for ev in events:
            fh.write(json_dumps(ev) + "\n")

def outbox_load() -> list[dict]:
    if not OUTBOX_PATH.exists():
        return []
    out: list[dict] = []
    for line in OUTBOX_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out

def outbox_rewrite(events: list[dict]) -> None:
    ensure_state_dir()
    tmp = OUTBOX_PATH.with_suffix(".jsonl.tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        for ev in events:
            fh.write(json_dumps(ev) + "\n")
    tmp.replace(OUTBOX_PATH)

def sent_ids_load() -> set[str]:
    if not SENT_IDS_PATH.exists():
        return set()
    return {ln.strip() for ln in SENT_IDS_PATH.read_text(encoding="utf-8").splitlines() if ln.strip()}

def sent_ids_save(ids: Iterable[str]) -> None:
    ensure_state_dir()
    text = "\n".join(sorted(set(ids)))
    if text:
        text += "\n"
    tmp = SENT_IDS_PATH.with_suffix(".ids.tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(SENT_IDS_PATH)

# --- Sender ------------------------------------------------------------------

# Tailnet cidrs covered by 100.64.0.0/10 — same rule the server uses.
TAILNET_NET = "100.64.0.0"
TAILNET_PREFIX = 10  # /10

def _ipv4_to_int(ip: str) -> int:
    parts = ip.split(".")
    if len(parts) != 4:
        raise ValueError(f"not an ipv4: {ip}")
    n = 0
    for p in parts:
        n = (n << 8) | int(p)
    return n

def in_tailnet(host: str) -> bool:
    """Return True if `host` parses as an IPv4 in 100.64.0.0/10."""
    try:
        n = _ipv4_to_int(host)
    except ValueError:
        return False
    mask = (0xFFFFFFFF << (32 - TAILNET_PREFIX)) & 0xFFFFFFFF
    base = _ipv4_to_int(TAILNET_NET)
    return (n & mask) == (base & mask)

def url_peer_in_tailnet(url: str) -> bool:
    """Best-effort: confirm the resolved socket peer is in 100.64.0.0/10.
    Used in offline/dry contexts. Real auth check belongs on the server.
    """
    from urllib.parse import urlparse
    p = urlparse(url)
    host = p.hostname or ""
    try:
        infos = socket.getaddrinfo(host, p.port or 0, type=socket.SOCK_STREAM)
    except Exception:
        return False
    for info in infos:
        sockaddr = info[4]
        ip = sockaddr[0]
        if ip.startswith("::ffff:"):
            ip = ip[len("::ffff:"):]
        if "." in ip and in_tailnet(ip):
            return True
    return False

def post_events(events: list[dict], url: str | None = None, timeout: float = 5.0,
                token: str | None = None, dry_run: bool = False) -> dict:
    """POST one event or {events:[...]} to the godhome ingest endpoint.

    Returns {"accepted": n, "duplicate": m} on success.
    Raises on transport failure so the caller can decide between outbox and retry.
    """
    url = url or env_url()
    token = token if token is not None else env_token()
    if dry_run:
        print(json_dumps(events[0] if len(events) == 1 else {"events": events}))
        return {"accepted": 0, "duplicate": 0, "dry_run": True}
    payload = events[0] if len(events) == 1 else {"events": events}
    data = json_dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={"Content-Type": "application/json",
                 "User-Agent": f"world-mac/{CONTRACT_VERSION}"},
    )
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace") or "{}"
            return json.loads(body)
    except urllib.error.HTTPError as e:
        # 4xx → re-sending won't help; surface the error so caller can drop
        raise RuntimeError(f"server rejected {e.code}: {e.read().decode('utf-8','replace')[:200]}")
    except (urllib.error.URLError, socket.timeout, OSError) as e:
        raise RuntimeError(f"transport: {e}")

def send(events: list[dict], url: str | None = None, timeout: float = 5.0,
         token: str | None = None, dry_run: bool = False,
         chunk: int = 500) -> dict:
    """Batched send with server-side dedupe by id."""
    accepted = 0
    duplicate = 0
    last: dict = {}
    for i in range(0, len(events), chunk):
        batch = events[i:i + chunk]
        rep = post_events(batch, url=url, timeout=timeout, token=token, dry_run=dry_run)
        accepted += int(rep.get("accepted", 0) or 0)
        duplicate += int(rep.get("duplicate", 0) or 0)
        last = rep
    last["accepted"] = accepted
    last["duplicate"] = duplicate
    return last

# --- Event builder -----------------------------------------------------------

VALID_KINDS = {"task", "commit", "pr", "review", "merge", "worker", "deploy",
               "alert", "recovery", "skill", "swot", "kb", "message", "status",
               "life", "source"}
VALID_STATUSES = {"done", "pending", "running", "failed", "up", "down", "stale"}

def event(*, id: str, ts: str, project: str, kind: str, status: str, title: str,
          ref: str = "", url: str = "", actor: str = "owner", model: str = "",
          cost: float | None = None, dur_s: float | None = None,
          source: str, host: str = HOST) -> dict:
    if kind not in VALID_KINDS:
        raise ValueError(f"bad kind: {kind}")
    if status not in VALID_STATUSES:
        raise ValueError(f"bad status: {status}")
    return {
        "id": id,
        "ts": ts,
        "host": host,
        "project": slug(project),
        "kind": kind,
        "status": status,
        "title": trim_title(scrub_title(title)),
        "ref": ref,
        "url": url,
        "actor": actor,
        "model": model,
        "cost": cost,
        "dur_s": dur_s,
        "source": source,
    }

# --- Filesystem helpers ------------------------------------------------------

WORKTREE_NEEDLES = (".worktrees/", "/.claude/worktrees/")

def looks_like_worktree(path: Path) -> bool:
    s = str(path)
    for n in WORKTREE_NEEDLES:
        if n in s:
            return True
    parts = s.split("/")
    for p in parts:
        if p.endswith("-wt") or p.endswith("-wt/") or p.startswith("FashionVerse-"):
            return True
        # Conservative: any directory that begins with 'FashionVerse-' anywhere
        if p.startswith("FashionVerse-"):
            return True
    return False

def iter_git_roots(roots: Iterable[str], max_depth: int = 3) -> Iterable[Path]:
    seen: set[str] = set()
    for root in roots:
        rp = Path(root)
        if not rp.exists():
            continue
        for cur, dirs, files in _walk(rp, max_depth):
            if ".git" in dirs or (cur / ".git").exists():
                if looks_like_worktree(cur):
                    dirs[:] = []
                    continue
                real = str(cur.resolve())
                if real in seen:
                    dirs[:] = []
                    continue
                seen.add(real)
                yield cur
                dirs[:] = []  # don't descend into nested git worktrees

_WALK_SKIP = {"node_modules", "vendor", "venv", "__pycache__", "dist", "build",
              "target", "Pods", "site-packages"}

def _walk(root: Path, max_depth: int):
    depth = 0
    stack = [(root, depth)]
    while stack:
        p, d = stack.pop()
        try:
            for entry in sorted(p.iterdir()):
                if entry.name.startswith(".") or entry.name in _WALK_SKIP:
                    continue
                if entry.is_dir():
                    try:
                        subdirs = [e.name for e in entry.iterdir() if e.is_dir()]
                    except OSError:
                        subdirs = []
                    yield (entry, subdirs, [])
                    if d + 1 <= max_depth:
                        stack.append((entry, d + 1))
        except (PermissionError, OSError):
            continue
