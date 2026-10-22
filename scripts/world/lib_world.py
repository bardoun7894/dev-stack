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
REJECTED_PATH = STATE_DIR / "rejected.jsonl"

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

def _cap_utf16_units(s: str, n: int) -> str:
    """Return `s` truncated to <= n UTF-16 code units, never splitting a surrogate pair.

    Uses the well-defined boundary that JS .length sees: each code unit is 2 bytes
    in UTF-16-LE, surrogate pairs count as 2. If cutting at exactly n would land
    between the high and low surrogate of a non-BMP code point, drop the pair.
    """
    if not s:
        return ""
    enc = s.encode("utf-16-le")
    max_bytes = n * 2
    if len(enc) <= max_bytes:
        return s
    cand = enc[:max_bytes]
    # Surrogate pair split? UTF-16 high surrogates live in 0xD800–0xDBFF, low in
    # 0xDC00–0xDFFF. In little-endian, the high surrogate is the LAST 2 bytes of
    # the slice when a split occurs.
    if len(cand) >= 2:
        hi = cand[-2] | (cand[-1] << 8)
        if 0xD800 <= hi <= 0xDBFF:
            cand = cand[:-2]
    return cand.decode("utf-16-le")

def trim_title(s: str, limit: int = 140) -> str:
    """Cap title by UTF-16 code units (server measures with JS .length).

    Empty result after the cap is replaced with '(untitled)'. When truncation
    actually happens, the result is `limit - 1` chars + 1 ellipsis, fitting
    exactly within `limit` UTF-16 code units.
    """
    s = (s or "").replace("\n", " ").strip()
    if not s:
        return "(untitled)"
    in_units = len(s.encode("utf-16-le")) // 2
    if in_units <= limit:
        return s
    # Truncated: take limit-1 units, then append '…' (1 unit) -> exactly `limit`.
    out = _cap_utf16_units(s, limit - 1)
    if not out:
        return "(untitled)"
    return out + "…"

# Server-side secret filters (src/server/world.ts). Copy exactly so any
# title that would 400 a batch gets neutralised before it leaves the box.
# Flags: only `xox[abprs]-` and `bearer` are case-insensitive on the server.
_SCRUB_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_-]{6,}", re.IGNORECASE),
    re.compile(r"ghp_[A-Za-z0-9]{6,}", re.IGNORECASE),
    re.compile(r"gh[ousr]_[A-Za-z0-9]{6,}", re.IGNORECASE),
    # Server: /xox[abprs]-/i. Eat the whole token, not just the prefix (a stray space here once let
    # `xoxb-…` through, and the server then 400'd the batch).
    re.compile(r"xox[abprs]-[A-Za-z0-9-]*", re.IGNORECASE),
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

def rejected_append(event: dict, error: str) -> None:
    """Append a rejected event (with the server error) to rejected.jsonl."""
    ensure_state_dir()
    with REJECTED_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json_dumps({"event": event, "error": error,
                             "ts": now_utc_iso()}) + "\n")

# Server-side length caps (JS .length → UTF-16 code units). Keep in sync with
# the server's validateEvent.
CAP_TITLE = 140
CAP_REF = 200
CAP_URL = 500
CAP_MODEL = 120
CAP_PROJECT = 80

def normalise_event_lengths(ev: dict) -> None:
    """In-place: scrub server-secret-like patterns and cap every length-limited
    field by UTF-16 code units. Apply to every event before send.
    """
    if isinstance(ev.get("title"), str):
        ev["title"] = trim_title(scrub_title(ev["title"]), CAP_TITLE)
    for k, cap in (("ref", CAP_REF), ("url", CAP_URL), ("model", CAP_MODEL)):
        v = ev.get(k)
        if isinstance(v, str) and v:
            ev[k] = _cap_utf16_units(v, cap)
    if isinstance(ev.get("project"), str) and ev["project"]:
        # project is already slugged; just cap.
        ev["project"] = _cap_utf16_units(ev["project"], CAP_PROJECT)

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

# 4xx answers that are about the endpoint or the credentials, not about the events: re-sending the
# same events later can succeed, so they must never move events to rejected.jsonl.
_NOT_PAYLOAD_4XX = {401, 403, 404, 405, 407, 408, 409, 425, 429}
_REJECTED_CODE_RE = re.compile(r"server rejected (\d{3})\b")

def payload_rejection(msg: str) -> bool:
    """True when a post_events() error says the server refused the events themselves (a 4xx such as
    400/413/422). 5xx, transport errors and auth/URL/rate-limit 4xx are retryable, never a rejection."""
    m = _REJECTED_CODE_RE.match(msg or "")
    return bool(m) and 400 <= int(m.group(1)) < 500 and int(m.group(1)) not in _NOT_PAYLOAD_4XX

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
    ev = {
        "id": id,
        "ts": ts,
        "host": host,
        "project": slug(project),
        "kind": kind,
        "status": status,
        "title": title,
        "ref": ref,
        "url": url,
        "actor": actor,
        "model": model,
        "cost": cost,
        "dur_s": dur_s,
        "source": source,
    }
    normalise_event_lengths(ev)
    return ev

# --- Filesystem helpers ------------------------------------------------------

WORKTREE_NEEDLES = (".worktrees/", "/.claude/worktrees/")

# Cache for canonical_project: maps absolute dir -> slug of the base repo.
# Lifetime: per-process; cleared on restart, which is fine — sub-second cost.
_CANONICAL_CACHE: dict[str, str] = {}


def canonical_project(p: Path | str) -> str:
    """Return the canonical project slug for a directory.

    For git repos (or worktrees), resolves the base repo via
    `git -C <dir> rev-parse --path-format=absolute --git-common-dir` and
    returns slug(parent_dir_name). This collapses
    `~/projects/FashionVerse-g-pricing` -> `fashionverse`,
    `~/projects/edunex-056-rewards` -> `edunex-golden-master-v1-0-0`, etc.

    For non-git dirs, falls back to slug(dir.name). Returns 'unknown' for
    empty / nonexistent / non-path inputs.
    """
    if p is None or p == "":
        return "unknown"
    try:
        path = Path(p).expanduser()
    except Exception:
        return "unknown"
    if not str(path) or str(path) in ("/", "."):
        return "unknown"
    if not path.exists():
        # The path might be a worktree's checkout whose .git is a file that
        # git can still resolve — try git first, then bail to slug of name.
        try:
            cp = subprocess.run(
                ["git", "-C", str(path), "rev-parse", "--path-format=absolute",
                 "--git-common-dir"],
                capture_output=True, text=True, timeout=5,
            )
            if cp.returncode == 0 and cp.stdout.strip():
                common = cp.stdout.strip()
                base = Path(common).parent
                return slug(base.name) if base.name else "unknown"
        except Exception:
            pass
        if path.name:
            return slug(path.name) if path.name else "unknown"
        return "unknown"
    real = str(path.resolve())
    if real in _CANONICAL_CACHE:
        return _CANONICAL_CACHE[real]
    proj = "unknown"
    try:
        cp = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "--path-format=absolute",
             "--git-common-dir"],
            capture_output=True, text=True, timeout=5,
        )
        if cp.returncode == 0 and cp.stdout.strip():
            common = cp.stdout.strip()
            base = Path(common).parent
            proj = slug(base.name) if base.name else slug(path.name)
        else:
            proj = slug(path.name) if path.name else "unknown"
    except Exception:
        proj = slug(path.name) if path.name else "unknown"
    if proj and proj != "unknown":
        _CANONICAL_CACHE[real] = proj
    return proj


def project_from_transcript_folder(folder: str) -> str:
    """Map a ~/.claude/projects/<encoded-path> folder to a project slug.

    Encoded paths look like `-Users-mohamedbardouni-projects-FashionVerse-g-pricing`
    (leading dash, slashes -> dashes). If the encoded path has no `projects`
    segment (e.g. `-Users-mohamedbardouni`, `-private-var-...`), the project is
    'me' (home-level / catch-all). Otherwise we canonicalise the last segment
    via canonical_project against a reconstructed path under the current home.
    """
    name = (folder or "").lstrip("-")
    if not name:
        return "me"
    parts = name.split("-")
    # No 'projects' segment in the path -> home-level folder -> 'me'.
    if "projects" not in parts:
        return "me"
    try:
        idx = parts.index("projects")
    except ValueError:
        return "me"
    # Skip a sub-segment right after 'projects' (e.g. scratchpad, private-var).
    if idx + 1 >= len(parts):
        return "me"
    last = parts[idx + 1:]
    if not last or not any(c.isalnum() for c in last[0]):
        return "me"
    reconstructed = Path.home() / "projects" / "-".join(last)
    return canonical_project(reconstructed)


def looks_like_worktree(path: Path) -> bool:
    """True for *true* worktree paths (the .worktrees/ shadow dirs and the
    `-wt` suffix convention). Feature copies like `FashionVerse-g-pricing`
    or `edunex-056-rewards` are NOT considered worktrees here — they are
    git worktrees of a base repo and should be canonicalised via
    `canonical_project` rather than skipped.
    """
    s = str(path)
    for n in WORKTREE_NEEDLES:
        if n in s:
            return True
    parts = s.split("/")
    for p in parts:
        if p.endswith("-wt") or p.endswith("-wt/"):
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
                # A linked worktree has a .git *file*; its main repo is scanned itself.
                if (cur / ".git").is_file() or looks_like_worktree(cur):
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
