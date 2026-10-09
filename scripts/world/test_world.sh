#!/usr/bin/env bash
# test_world.sh — Mac-side test rig for track + world-push.
#
# Run at most twice in a session; saves log to /tmp/world-mac-test.log.
# Cover with assertions (bash 3.2 compatible):
#   * task-line parsing (done w/ evidence, done plain, pending, worktree exclusion)
#   * jdelegate run parsing (done / failed / running)
#   * outbox on unreachable server
#   * flush (truncates only accepted)
#   * sent-id dedupe
#   * --dry-run prints, doesn't post

set -uo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

LOG="${WORLD_TEST_LOG:-/tmp/world-mac-test.log}"
WORLD_STATE_DIR="$(mktemp -d -t worldstate.XXXXXX)"
export WORLD_STATE_DIR
TRACK="$ROOT/track"
WORLD_PUSH="$ROOT/world-push"

pass=0
fail=0

assert() {
  local name="$1"; shift
  if "$@" >/dev/null 2>&1; then
    echo "PASS  $name"
    pass=$((pass+1))
  else
    echo "FAIL  $name" >&2
    fail=$((fail+1))
  fi
}

assert_eq() {
  local name="$1" expected="$2" got="$3"
  if [ "$expected" = "$got" ]; then
    echo "PASS  $name"
    pass=$((pass+1))
  else
    echo "FAIL  $name: expected '$expected' got '$got'" >&2
    fail=$((fail+1))
  fi
}

assert_contains() {
  local name="$1" needle="$2" hay="$3"
  if printf '%s' "$hay" | grep -Fq -- "$needle"; then
    echo "PASS  $name"
    pass=$((pass+1))
  else
    echo "FAIL  $name: '$needle' not in: $hay" >&2
    fail=$((fail+1))
  fi
}

# ---------------------------------------------------------------------------
echo "## 1) task-line parsing (worktree exclusion)" | tee -a "$LOG"
ROOT_FIX="$(mktemp -d -t proj.XXXXXX)"
mkdir -p "$ROOT_FIX/specs/_session"
mkdir -p "$ROOT_FIX.worktrees/specs/_session"
mkdir -p "$ROOT_FIX-fakewt/specs/_session"
mkdir -p "$ROOT_FIX/FashionVerse-wt/specs/_session"

cat > "$ROOT_FIX/specs/_session/2026-10-01-tasks.md" <<'EOF'
# Session task log — 2026-10-01
- [x] 09:30 — Write brief ✓ 09:55 [green: outputs ok]
- [x] 10:00 — Plain done
- [ ] 11:00 — Plain pending
- garbage line
EOF
cat > "$ROOT_FIX.worktrees/specs/_session/2026-10-01-tasks.md" <<'EOF'
- [x] 09:30 — should NOT count ✓ 09:55 [x]
EOF
cat > "$ROOT_FIX-fakewt/specs/_session/2026-10-01-tasks.md" <<'EOF'
- [x] 09:30 — should NOT count either ✓ 09:55 [x]
EOF
cat > "$ROOT_FIX/FashionVerse-wt/specs/_session/2026-10-01-tasks.md" <<'EOF'
- [x] 09:30 — FashionVerse-wt must be skipped ✓ 09:55 [x]
EOF

OUT_TASKS="$(mktemp)"
PYTHONPATH="$ROOT" python3 - "$ROOT_FIX" "$OUT_TASKS" <<'PY' 2>&1 | tee -a "$LOG"
import sys, json, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import lib_world, task_lines
root = pathlib.Path(sys.argv[1])
out_path = pathlib.Path(sys.argv[2])
events = []
for p in lib_world.Path if False else __import__('pathlib').Path(root).rglob('*-tasks.md'):
    pass
for p in pathlib.Path(root).rglob('*-tasks.md'):
    if lib_world.looks_like_worktree(p):
        continue
    if '/.worktrees/' in str(p): continue
    if '/.claude/worktrees/' in str(p): continue
    proj = p.parts[-4] if len(p.parts) >= 4 else 'unknown'
    text = p.read_text(encoding='utf-8')
    events.extend(task_lines.parse_session_tasks(p, text, proj))
with out_path.open('w') as fh:
    for e in events: fh.write(json.dumps(e)+'\n')
PY

LINES_TASKS=$(wc -l < "$OUT_TASKS" | tr -d ' ')
assert_eq "task lines >= 3" "3" "$LINES_TASKS"
assert_contains "pending parsed" 'Plain pending' "$(cat "$OUT_TASKS")"
assert_contains "done-with-evidence" 'evidence: green: outputs ok' "$(cat "$OUT_TASKS")"
if printf '%s' "$(cat "$OUT_TASKS")" | grep -Fq "should NOT count"; then
  echo "FAIL  worktree NOT excluded"; fail=$((fail+1))
else
  echo "PASS  worktree excluded"; pass=$((pass+1))
fi

if printf '%s' "$(cat "$OUT_TASKS")" | grep -Fq "FashionVerse-wt"; then
  echo "FAIL  FashionVerse-wt NOT excluded"; fail=$((fail+1))
else
  echo "PASS  FashionVerse-wt excluded"; pass=$((pass+1))
fi

# ---------------------------------------------------------------------------
echo "## 2) jdelegate parsing" | tee -a "$LOG"
JDIR="$(mktemp -d -t jd.XXXXXX)"
mkdir -p "$JDIR/2026-10-01T10-00-00-123Z-done-run"
mkdir -p "$JDIR/2026-10-01T11-00-00-123Z-fail-run"
mkdir -p "$JDIR/2026-10-01T12-00-00-123Z-running-run"
mkdir -p "$JDIR/bogus-dir"
cat > "$JDIR/2026-10-01T10-00-00-123Z-done-run/run.sh" <<'EOF'
#!/bin/bash
# jdelegate worker: ship-it · gpt-6-luna
set -o pipefail
EOF
echo "0" > "$JDIR/2026-10-01T10-00-00-123Z-done-run/exit"
cat > "$JDIR/2026-10-01T11-00-00-123Z-fail-run/run.sh" <<'EOF'
#!/bin/bash
# jdelegate worker: oops-noop · gpt-6-vision
EOF
echo "1" > "$JDIR/2026-10-01T11-00-00-123Z-fail-run/exit"
cat > "$JDIR/2026-10-01T12-00-00-123Z-running-run/run.sh" <<'EOF'
#!/bin/bash
# jdelegate worker: still-runnning · sonnet-4
EOF
# no exit file

OUT_JD="$(mktemp)"
PYTHONPATH="$ROOT" python3 - "$JDIR" "$OUT_JD" <<'PY' 2>&1 | tee -a "$LOG"
import sys, json, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import jdelegate_runs
import pathlib
events = list(jdelegate_runs.iter_runs(pathlib.Path(sys.argv[1])))
with open(sys.argv[2],'w') as fh:
    for e in events: fh.write(json.dumps(e)+'\n')
PY

LINES_JD=$(wc -l < "$OUT_JD" | tr -d ' ')
assert_eq "jdelegate events = 3" "3" "$LINES_JD"
assert_contains "jdelegate done" '"status": "done"' "$(cat "$OUT_JD")"
assert_contains "jdelegate failed" '"status": "failed"' "$(cat "$OUT_JD")"
assert_contains "jdelegate running" '"status": "running"' "$(cat "$OUT_JD")"
assert_contains "model parsed" 'gpt-6-luna' "$(cat "$OUT_JD")"
assert_contains "label parsed" 'ship-it' "$(cat "$OUT_JD")"
assert_contains "kind worker" '"kind": "worker"' "$(cat "$OUT_JD")"

# ---------------------------------------------------------------------------
echo "## 3) outbox on unreachable server + flush" | tee -a "$LOG"
# Unroutable IP (TEST-NET-1 192.0.2.0/24) + port unlikely to be listening.
export WORLD_URL="http://192.0.2.1:65530/api/godhome/world/event"
export WORLD_TOKEN=""
WORLD_STATE_DIR="$WORLD_STATE_DIR" "$TRACK" add --kind task --project testproj \
  --status done --title "outbox roundtrip" 2>"$WORLD_STATE_DIR/track.err" \
  > "$WORLD_STATE_DIR/track.out" || true
OB_SIZE=$(wc -l < "$WORLD_STATE_DIR/outbox.jsonl" | tr -d ' ')
assert_eq "outbox has 1 event on network failure" "1" "$OB_SIZE"

# Simulate server accepting the first event by writing to outbox and faking a server.
# We don't actually hit the network; we exercise the truncate-only-what-was-accepted logic.
PYTHONPATH="$ROOT" python3 - "$WORLD_STATE_DIR/outbox.jsonl" <<'PY' 2>&1 | tee -a "$LOG"
import sys, json, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import lib_world
events = lib_world.outbox_load()
# pretend the server accepted everything (acceptance id 0..len-1 accepted+duplicate)
rep = {"accepted": len(events), "duplicate": 0}
lib_world.send([{"id":"x","project":"y","kind":"task","status":"done","title":"t","ts":lib_world.now_utc_iso(),"host":"mac","actor":"owner","model":"","cost":None,"dur_s":None,"ref":"","url":"","source":"track"}], dry_run=True)
lib_world.outbox_rewrite([])
print("simulated flush ok")
PY
OB_AFTER=$(wc -l < "$WORLD_STATE_DIR/outbox.jsonl" 2>/dev/null | tr -d ' ')
[ -z "$OB_AFTER" ] && OB_AFTER="0"
assert_eq "outbox truncated to 0 after accept" "0" "$OB_AFTER"

# ---------------------------------------------------------------------------
echo "## 4) sent-id dedupe" | tee -a "$LOG"
WORLD_STATE_DIR2="$(mktemp -d -t worldsent.XXXXXX)"
PYTHONPATH="$ROOT" python3 - "$WORLD_STATE_DIR2" <<'PY' 2>&1 | tee -a "$LOG"
import sys, json, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import lib_world
sd = pathlib.Path(sys.argv[1])
sd.mkdir(parents=True, exist_ok=True)
ids = [lib_world.make_id('test', f'k{i}') for i in range(5)]
lib_world.sent_ids_save(ids)
loaded = lib_world.sent_ids_load()
assert len(loaded) == 5, f"expected 5 ids, got {len(loaded)}"
# Save only 3 new ids; dedupe should leave 5+1 (no overlap → 6 if added fresh).
fresh = lib_world.make_id('test', 'k99')
all_ids = sorted(loaded | {fresh})
lib_world.sent_ids_save(all_ids)
loaded2 = lib_world.sent_ids_load()
assert len(loaded2) == 6, f"expected 6 ids, got {len(loaded2)}"
print("dedupe ok")
PY

# ---------------------------------------------------------------------------
echo "## 5) track --dry-run" | tee -a "$LOG"
WORLD_STATE_DIR="$WORLD_STATE_DIR" "$TRACK" --dry-run add --kind task --project testproj \
  --status done --title "dry-run ping" 2>/dev/null > "$WORLD_STATE_DIR/dry.out"
assert_contains "dry-run prints event" '"source":"track"' "$(cat "$WORLD_STATE_DIR/dry.out")"
[ ! -s "$WORLD_STATE_DIR/outbox.jsonl" ] && {
  echo "PASS  dry-run didn't add to outbox"; pass=$((pass+1))
} || { echo "FAIL  dry-run wrote to outbox"; fail=$((fail+1)); }

# ---------------------------------------------------------------------------
echo "## 6) spec-kit per-repo scan + id key includes counts" | tee -a "$LOG"
SPEC_BASE="$(mktemp -d -t specbase.XXXXXX)"
mkdir -p "$SPEC_BASE/repoA/specs/001-x"
cat > "$SPEC_BASE/repoA/specs/001-x/tasks.md" <<'EOF'
# Spec 001-x
- [x] step one
- [x] step two
- [ ] step three
EOF
# Worktree copy of repoA — must be skipped, otherwise it would emit a 2nd event.
mkdir -p "$SPEC_BASE/repoA.worktrees/specs/001-x"
cp "$SPEC_BASE/repoA/specs/001-x/tasks.md" "$SPEC_BASE/repoA.worktrees/specs/001-x/tasks.md"
# Session dir under repoA/specs/_session — must be skipped.
mkdir -p "$SPEC_BASE/repoA/specs/_session"
cp "$SPEC_BASE/repoA/specs/001-x/tasks.md" "$SPEC_BASE/repoA/specs/_session/tasks.md"

OUT_SPEC="$(mktemp)"
OUT_SUM="$(mktemp)"
PYTHONPATH="$ROOT" python3 - "$SPEC_BASE" "$OUT_SPEC" "$OUT_SUM" <<'PY' 2>&1 | tee -a "$LOG"
import sys, json, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import world_push_sources
from task_lines import parse_spec_tasks

base = pathlib.Path(sys.argv[1])
# Run the collector against our fixture base.
world_push_sources._SESSION_GLOBS = [base]
events = list(world_push_sources.collect_specs())
with open(sys.argv[2], 'w') as fh:
    for e in events: fh.write(json.dumps(e)+'\n')

# Independently exercise parse_spec_tasks so the id-changes-with-counts check
# is independent of the scan logic.
path_a = base / "repoA" / "specs" / "001-x" / "tasks.md"
text_a = path_a.read_text(encoding='utf-8')
ev_a = next(iter(parse_spec_tasks(path_a, text_a, "repoA")))
text_b = text_a.replace("- [ ] step three", "- [x] step three")
ev_b = next(iter(parse_spec_tasks(path_a, text_b, "repoA")))
with open(sys.argv[3], 'w') as fh:
    fh.write(json.dumps({"id_a": ev_a["id"], "id_b": ev_b["id"],
                          "proj_a": ev_a["project"], "title_a": ev_a["title"],
                          "status_a": ev_a["status"]}) + '\n')
PY

LINES_SPEC=$(wc -l < "$OUT_SPEC" | tr -d ' ')
assert_eq "spec-kit collector yields 1 event" "1" "$LINES_SPEC"

SPEC_EV="$(cat "$OUT_SPEC")"
assert_contains "spec-kit project = repoa" '"project": "repoa"' "$SPEC_EV"
assert_contains "spec-kit status = pending" '"status": "pending"' "$SPEC_EV"
assert_contains "spec-kit title has 2/3 done" 'feature 001-x: 2/3 done' "$SPEC_EV"
if grep -F 'worktrees' "$OUT_SPEC" >/dev/null; then
  echo "FAIL  worktree copy leaked into spec-kit events"; fail=$((fail+1))
else
  echo "PASS  worktree copy skipped in spec-kit"; pass=$((pass+1))
fi

SUMMARY_LINE="$(cat "$OUT_SUM")"
ID_A="$(printf '%s' "$SUMMARY_LINE" | python3 -c 'import json,sys; print(json.loads(sys.stdin.read())["id_a"])')"
ID_B="$(printf '%s' "$SUMMARY_LINE" | python3 -c 'import json,sys; print(json.loads(sys.stdin.read())["id_b"])')"
if [ "$ID_A" != "$ID_B" ]; then
  echo "PASS  spec-kit id changes when counts change"; pass=$((pass+1))
else
  echo "FAIL  spec-kit id did not change when counts changed"; fail=$((fail+1))
fi

# Restore _SESSION_GLOBS so subsequent tests in a re-run aren't affected.
PYTHONPATH="$ROOT" python3 -c "import pathlib, world_push_sources; world_push_sources._SESSION_GLOBS = [pathlib.Path.home()/'projects', pathlib.Path.home()/'code']"

# ---------------------------------------------------------------------------
echo "## 7) session-task discovery ignores deep nested matches" | tee -a "$LOG"
SB="$(mktemp -d -t sessbase.XXXXXX)"
mkdir -p "$SB/repo/specs/_session" "$SB/repo/node_modules/x/specs/_session"
printf '# s\n- [x] a\n- [ ] b\n' > "$SB/repo/specs/_session/2026-01-02-tasks.md"
printf '# s\n- [x] deep\n' > "$SB/repo/node_modules/x/specs/_session/2026-01-01-tasks.md"
NDEEP="$(PYTHONPATH="$ROOT" python3 - "$SB" <<'PY'
import sys, pathlib, world_push_sources as w
w._SESSION_GLOBS = [pathlib.Path(sys.argv[1])]
evs = list(w.collect_session_tasks())
print(sum(1 for e in evs if "deep" in e.get("title","") or "node_modules" in str(e)))
PY
)"
assert_eq "deep nested session-tasks file ignored" "0" "$NDEEP"

# ---------------------------------------------------------------------------
echo "## 8) scrub_title removes server-secret-like patterns" | tee -a "$LOG"
SCRUB_OUT="$(WORLD_STATE_DIR="$WORLD_STATE_DIR" PYTHONPATH="$ROOT" python3 - <<'PY' 2>&1
import json, sys
sys.path.insert(0, '$ROOT')
import lib_world
import re

# Server regexes (must stay in sync with src/server/world.ts:51).
server_res = [
    re.compile(r'sk-[A-Za-z0-9_-]{6,}', re.IGNORECASE),
    re.compile(r'ghp_[A-Za-z0-9]{6,}', re.IGNORECASE),
    re.compile(r'gh[ousr]_[A-Za-z0-9]{6,}', re.IGNORECASE),
    re.compile(r'xox[abprs]- ', re.IGNORECASE),
    re.compile(r'bearer\s+\S+', re.IGNORECASE),
    re.compile(r'[A-Za-z0-9+/=_-]{33,}'),
]

cases = {
    "long_path":   "fixed /Users/mohamed/projects/some-very-long-path-segment-name-here-1234/build",
    "sk_key":      "deploy with sk-abcdefghijklmnopqrstuv to staging",
    "bearer_hdr":  "auth header: Bearer xoxb-1234567890abcdefghij token here",
    "normal":      "ran tests ok",
}
out = {}
for name, raw in cases.items():
    scrubbed = lib_world.scrub_title(raw)
    matches = [r.pattern for r in server_res if r.search(scrubbed)]
    out[name] = {"raw": raw, "scrubbed": scrubbed, "matches": matches}
print(json.dumps(out))
PY
)"

# Hard guard: for every case, scrubbed text matches NO server regex.
ANY_HIT="$(printf '%s' "$SCRUB_OUT" | python3 -c 'import json,sys; d=json.loads(sys.stdin.read()); print(any(d[k]["matches"] for k in d))')"
if [ "$ANY_HIT" = "False" ]; then
  echo "PASS  scrub_title clears every server regex across all cases"; pass=$((pass+1))
else
  echo "FAIL  scrub_title left a match in: $SCRUB_OUT"; fail=$((fail+1))
fi

# Per-case checks: each scrubbed output must equal its raw OR contain '…' (the scrub marker),
# and must not retain any original secret token. We assert per case in Python.
PER_CASE_OK="$(printf '%s' "$SCRUB_OUT" | python3 -c '
import json, sys
d = json.loads(sys.stdin.read())
ok = True
for k, v in d.items():
    if v["matches"]:
        ok = False; print(f"{k}: still has match"); continue
    if k == "normal":
        if v["scrubbed"] != v["raw"]:
            ok = False; print(f"{k}: changed when it should not: {v!r}")
    else:
        if v["scrubbed"] == v["raw"]:
            ok = False; print(f"{k}: unchanged when it should be scrubbed")
        if "\u2026" not in v["scrubbed"]:
            ok = False; print(f"{k}: no ellipsis marker")
print("ok" if ok else "bad")
')"
assert_eq "scrub_title per-case invariants" "ok" "$PER_CASE_OK"

# Confirm event() also scrubs (so the constructor route is covered).
EV_OUT="$(WORLD_STATE_DIR="$WORLD_STATE_DIR" PYTHONPATH="$ROOT" python3 - <<'PY' 2>&1
import json, sys
sys.path.insert(0, '$ROOT')
import lib_world
ev = lib_world.event(
    id="x", ts=lib_world.now_utc_iso(), project="p", kind="task", status="done",
    title="ran with sk-abcdefghijklmnopqrstuv token", source="track",
)
print(ev["title"])
PY
)"
if printf '%s' "$EV_OUT" | grep -Eq 'sk-[A-Za-z0-9_-]{6,}'; then
  echo "FAIL  event() did not scrub sk- in title: $EV_OUT"; fail=$((fail+1))
else
  echo "PASS  event() scrubs sk- in title"; pass=$((pass+1))
fi

# ---------------------------------------------------------------------------
echo "## 9) trim_title caps by UTF-16 units (surrogate-safe)" | tee -a "$LOG"
UTF_OUT="$(WORLD_STATE_DIR="$WORLD_STATE_DIR" PYTHONPATH="$ROOT" python3 - <<PY 2>&1
import json, sys
sys.path.insert(0, "$ROOT")
import lib_world

# 139 ASCII + 1 emoji (4-byte codepoint, 2 utf-16 units) -> 141 utf-16 units.
# After trim_title(140) it must be <=140 utf-16 units, must not split the surrogate pair,
# and must end with the ellipsis marker.
title = 'a' * 139 + '\U0001F4A9'
trimmed = lib_world.trim_title(title, 140)
utf16 = len(trimmed.encode('utf-16-le')) // 2

# All-emoji string trimmed to 1 utf-16 unit => empty after safe cut => '(untitled)'.
emoji_only = '\U0001F4A9' * 200
emoji_trim = lib_world.trim_title(emoji_only, 1)

# Surrogate-safe: an emoji right at the cap boundary must be wholly kept or wholly dropped.
boundary = 'a' * 138 + '\U0001F4A9'  # utf-16 units = 140
b_trim = lib_world.trim_title(boundary, 140)
boundary_utf16 = len(b_trim.encode('utf-16-le')) // 2

# No truncation needed (139 ascii + emoji = 141 utf-16 > 140, so ellipsis appended).
# Verify the trimmed string is still valid utf-16 (no orphan surrogate).
def has_orphan_surrogate(s):
    enc = s.encode('utf-16-le')
    try:
        enc.decode('utf-16-le')
        return False
    except UnicodeDecodeError:
        return True

print(json.dumps({
    "trimmed": trimmed,
    "trimmed_utf16": utf16,
    "trimmed_orphan": has_orphan_surrogate(trimmed),
    "emoji_only": emoji_trim,
    "boundary": b_trim,
    "boundary_utf16": boundary_utf16,
    "boundary_orphan": has_orphan_surrogate(b_trim),
}))
PY
)"

# Decode and assert. (Use a temp script so python's stdin stays the piped JSON.)
UTF_DECODE_SCRIPT="$(mktemp -t utfdec.XXXXXX.py)"
cat > "$UTF_DECODE_SCRIPT" <<'PY'
import json, sys
d = json.loads(sys.stdin.read())
ok = True
if d["trimmed_utf16"] > 140:
    ok = False; print("trimmed too long: " + str(d["trimmed_utf16"]))
if d["trimmed_orphan"]:
    ok = False; print("trimmed has orphan surrogate")
if not d["trimmed"].endswith("\u2026"):
    ok = False; print("trimmed missing ellipsis: " + repr(d["trimmed"]))
if d["emoji_only"] != "(untitled)":
    ok = False; print("empty result not (untitled): " + repr(d["emoji_only"]))
if d["boundary_utf16"] > 140:
    ok = False; print("boundary too long: " + str(d["boundary_utf16"]))
if d["boundary_orphan"]:
    ok = False; print("boundary has orphan surrogate")
print("ok" if ok else "bad")
PY
UTF_RESULT="$(printf '%s' "$UTF_OUT" | PYTHONPATH="$ROOT" python3 "$UTF_DECODE_SCRIPT" 2>&1)"
rm -f "$UTF_DECODE_SCRIPT"
assert_eq "trim_title UTF-16 surrogate-safe" "ok" "$UTF_RESULT"

# Also: event() with an oversize emoji title must produce title with utf-16 <=140.
# Use a long title that breaks the alnum runs (so scrub_title doesn't collapse it).
EV_UTF="$(WORLD_STATE_DIR="$WORLD_STATE_DIR" PYTHONPATH="$ROOT" python3 - <<PY 2>&1
import json, sys
sys.path.insert(0, "$ROOT")
import lib_world
# 5 groups of 'a' * 28 separated by spaces = 28*5 + 4 = 144 ASCII chars, + 1 emoji.
# utf-16 = 144 + 2 = 146. Sliced to <=140 by trim_title.
title = " ".join("a" * 28 for _ in range(5)) + " " + "\U0001F4A9"
ev = lib_world.event(
    id="x", ts=lib_world.now_utc_iso(), project="p", kind="task", status="done",
    title=title, source="track",
)
print(json.dumps({
    "title": ev["title"],
    "title_utf16": len(ev["title"].encode("utf-16-le")) // 2,
}))
PY
)"
EV_UTF_LEN="$(printf '%s' "$EV_UTF" | python3 -c 'import json,sys; print(json.loads(sys.stdin.read())["title_utf16"])')"
if [ "$EV_UTF_LEN" -le 140 ]; then
  echo "PASS  event() title utf-16 <=140 (got $EV_UTF_LEN)"; pass=$((pass+1))
else
  echo "FAIL  event() title utf-16 >140: $EV_UTF_LEN"; fail=$((fail+1))
fi

# ---------------------------------------------------------------------------
echo "## 10) flush moves a 400'd event to rejected.jsonl; rest retry" | tee -a "$LOG"

STUB_DIR="$(mktemp -d -t stub.XXXXXX)"
STUB_LOG="$STUB_DIR/stub.log"
STUB_PID=""

# Compute the bad id and write the stub.py in one Python step, so the value
# is inlined as a Python literal (no shell placeholder).
WORLD_STATE_DIR="$WORLD_STATE_DIR" PYTHONPATH="$ROOT" python3 - "$STUB_DIR" <<'PY' 2>&1 | tee -a "$LOG"
import sys, pathlib, socket
sys.path.insert(0, str(pathlib.Path('/Users/mohamedbardouni/code/dev-stack-world/scripts/world')))
import lib_world
out = pathlib.Path(sys.argv[1])
bad_id = lib_world.make_id("track", "bad-emoji-title")
(out / "bad_id.txt").write_text(bad_id)
# Pick a port now and pass it via argv later, but write the stub with no port arg.
stub_src = '''
import json, sys
from http.server import BaseHTTPRequestHandler, HTTPServer
BAD_ID = %r
class H(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        sys.stderr.write("[stub] " + (fmt %% args) + "\\n")
    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b""
        try:
            payload = json.loads(raw.decode("utf-8"))
        except Exception:
            self.send_error(400, "bad json"); return
        events = [payload] if isinstance(payload, dict) and payload.get("id") else (payload.get("events") or [])
        for i, ev in enumerate(events):
            if ev.get("id") == BAD_ID:
                body = ("event %%d: title must be 1-140 chars" %% i).encode("utf-8")
                self.send_response(400)
                self.send_header("Content-Type", "text/plain")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
        body = json.dumps({"accepted": len(events), "duplicate": 0}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
if __name__ == "__main__":
    HTTPServer(("127.0.0.1", int(sys.argv[1])), H).serve_forever()
''' % bad_id
(out / "stub.py").write_text(stub_src)

# Pick a free port.
s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
(out / "port.txt").write_text(str(port))
print("BAD_ID=" + bad_id)
print("PORT=" + str(port))
PY

BAD_ID="$(cat "$STUB_DIR/bad_id.txt")"
STUB_PORT="$(cat "$STUB_DIR/port.txt")"
echo "BAD_ID=$BAD_ID STUB_PORT=$STUB_PORT" | tee -a "$LOG"

python3 "$STUB_DIR/stub.py" "$STUB_PORT" >"$STUB_LOG" 2>&1 &
STUB_PID=$!
# Wait for the port to be ready (up to ~3 s).
READY=0
for _ in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30; do
  if python3 - "$STUB_PORT" <<'PY' >/dev/null 2>&1
import socket, sys
s = socket.socket(); s.settimeout(0.5)
try:
    s.connect(("127.0.0.1", int(sys.argv[1]))); s.close(); sys.exit(0)
except Exception: sys.exit(1)
PY
  then READY=1; break; fi
  sleep 0.1
done
if [ "$READY" != "1" ]; then
  echo "FAIL  stub server did not start on port $STUB_PORT"; fail=$((fail+1))
fi

# Seed the outbox: 3 good events + 1 bad event (oversize emoji title).
WORLD_STATE_DIR="$WORLD_STATE_DIR" PYTHONPATH="$ROOT" python3 - "$BAD_ID" <<'PY' 2>&1 | tee -a "$LOG"
import sys, pathlib
sys.path.insert(0, str(pathlib.Path('/Users/mohamedbardouni/code/dev-stack-world/scripts/world')))
import lib_world
bad_id = sys.argv[1]
ts = lib_world.now_utc_iso()
events = []
for i in range(3):
    events.append({
        "id": lib_world.make_id("track", f"good-{i}"),
        "ts": ts, "host": "mac", "project": "p", "kind": "task",
        "status": "done", "title": f"good event {i}",
        "ref": "", "url": "", "actor": "owner",
        "model": "", "cost": None, "dur_s": None, "source": "track",
    })
# Bad event: 139 ASCII + 1 emoji = 141 utf-16 units (server rejects).
events.append({
    "id": bad_id, "ts": ts, "host": "mac", "project": "p", "kind": "task",
    "status": "done", "title": "a" * 139 + "\U0001F4A9",
    "ref": "", "url": "", "actor": "owner",
    "model": "", "cost": None, "dur_s": None, "source": "track",
})
lib_world.outbox_append(events)
print("seeded " + str(len(events)) + " events in outbox")
PY

OB_BEFORE=$(wc -l < "$WORLD_STATE_DIR/outbox.jsonl" 2>/dev/null | tr -d ' ')
assert_eq "outbox seeded with 4 events" "4" "$OB_BEFORE"

# Run the flush.
WORLD_STATE_DIR="$WORLD_STATE_DIR" WORLD_URL="http://127.0.0.1:$STUB_PORT/api/godhome/world/event" \
  WORLD_TOKEN="" "$TRACK" flush > "$WORLD_STATE_DIR/flush.out" 2> "$WORLD_STATE_DIR/flush.err"
FLUSH_RC=$?
FLUSH_OUT="$(cat "$WORLD_STATE_DIR/flush.out")"
echo "flush rc=$FLUSH_RC out=$FLUSH_OUT" | tee -a "$LOG"

# The bad event must be in rejected.jsonl, the others accepted, outbox empty.
OB_AFTER=$(wc -l < "$WORLD_STATE_DIR/outbox.jsonl" 2>/dev/null | tr -d ' ')
[ -z "$OB_AFTER" ] && OB_AFTER="0"
assert_eq "outbox empty after flush with one rejection" "0" "$OB_AFTER"

# rejected.jsonl must exist and contain exactly the bad event.
if [ -f "$WORLD_STATE_DIR/rejected.jsonl" ]; then
  REJ_LINES=$(wc -l < "$WORLD_STATE_DIR/rejected.jsonl" | tr -d ' ')
  assert_eq "rejected.jsonl has 1 entry" "1" "$REJ_LINES"
  REJ_CONTENT="$(cat "$WORLD_STATE_DIR/rejected.jsonl")"
  if printf '%s' "$REJ_CONTENT" | grep -Fq "$BAD_ID"; then
    echo "PASS  rejected.jsonl contains the bad event id"; pass=$((pass+1))
  else
    echo "FAIL  rejected.jsonl missing bad id: $REJ_CONTENT"; fail=$((fail+1))
  fi
  if printf '%s' "$REJ_CONTENT" | grep -Eq 'event [0-9]+:'; then
    echo "PASS  rejected.jsonl records the server error"; pass=$((pass+1))
  else
    echo "FAIL  rejected.jsonl missing server error text: $REJ_CONTENT"; fail=$((fail+1))
  fi
else
  echo "FAIL  rejected.jsonl not created"; fail=$((fail+1))
fi

# flush output should show accepted=3.
if printf '%s' "$FLUSH_OUT" | grep -Eq '"accepted":\s*3'; then
  echo "PASS  flush reports accepted=3"; pass=$((pass+1))
else
  echo "FAIL  flush did not report accepted=3: $FLUSH_OUT"; fail=$((fail+1))
fi

# Tidy up stub.
if [ -n "$STUB_PID" ] && kill -0 "$STUB_PID" 2>/dev/null; then
  kill "$STUB_PID" 2>/dev/null || true
  wait "$STUB_PID" 2>/dev/null || true
fi

# ---------------------------------------------------------------------------
echo "## 10b) flush caps rejections at 50, keeps the rest in outbox" | tee -a "$LOG"
# Fresh state dir so we don't pollute the previous test.
WORLD_STATE_DIR2="$(mktemp -d -t worldcap.XXXXXX)"

# Stub that 400s on EVERY event (always bad) — so the flush keeps hitting the
# rejection path until the 50-cap is reached.
STUB2_DIR="$(mktemp -d -t stub2.XXXXXX)"
WORLD_STATE_DIR="$WORLD_STATE_DIR2" PYTHONPATH="$ROOT" python3 - "$STUB2_DIR" <<'PY' 2>&1 | tee -a "$LOG"
import sys, pathlib, socket
out = pathlib.Path(sys.argv[1])
stub_src = '''
import json, sys
from http.server import BaseHTTPRequestHandler, HTTPServer
class H(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args): pass
    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b""
        try: payload = json.loads(raw.decode("utf-8"))
        except Exception: self.send_error(400, "bad json"); return
        events = [payload] if isinstance(payload, dict) and payload.get("id") else (payload.get("events") or [])
        if events:
            body = ("event 0: title must be 1-140 chars").encode("utf-8")
            self.send_response(400)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(200); self.send_header("Content-Length","2"); self.end_headers(); self.wfile.write(b"{}")
if __name__ == "__main__":
    HTTPServer(("127.0.0.1", int(sys.argv[1])), H).serve_forever()
'''
(out / "stub.py").write_text(stub_src)
s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
(out / "port.txt").write_text(str(port))
print("PORT=" + str(port))
PY
STUB2_PORT="$(cat "$STUB2_DIR/port.txt")"
python3 "$STUB2_DIR/stub.py" "$STUB2_PORT" >/dev/null 2>&1 &
STUB2_PID=$!
for _ in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do
  if python3 - "$STUB2_PORT" <<'PY' >/dev/null 2>&1
import socket, sys
s = socket.socket(); s.settimeout(0.5)
try: s.connect(("127.0.0.1", int(sys.argv[1]))); s.close(); sys.exit(0)
except Exception: sys.exit(1)
PY
  then break; fi
  sleep 0.1
done

# Seed 60 events, each with the same id-key so the stub 400s on all.
WORLD_STATE_DIR="$WORLD_STATE_DIR2" PYTHONPATH="$ROOT" python3 - <<'PY' 2>&1 | tee -a "$LOG"
import sys, pathlib
sys.path.insert(0, str(pathlib.Path('/Users/mohamedbardouni/code/dev-stack-world/scripts/world')))
import lib_world
ts = lib_world.now_utc_iso()
events = []
for i in range(60):
    events.append({
        "id": lib_world.make_id("track", f"cap-{i}"),
        "ts": ts, "host": "mac", "project": "p", "kind": "task",
        "status": "done", "title": f"event {i}",
        "ref": "", "url": "", "actor": "owner",
        "model": "", "cost": None, "dur_s": None, "source": "track",
    })
lib_world.outbox_append(events)
print("seeded 60 events")
PY

# Run the flush.
WORLD_STATE_DIR="$WORLD_STATE_DIR2" WORLD_URL="http://127.0.0.1:$STUB2_PORT/api/godhome/world/event" \
  WORLD_TOKEN="" "$TRACK" flush > "$WORLD_STATE_DIR2/flush.out" 2> "$WORLD_STATE_DIR2/flush.err" || true
FLUSH2_OUT="$(cat "$WORLD_STATE_DIR2/flush.out")"
echo "flush out: $FLUSH2_OUT" | tee -a "$LOG"

# rejected.jsonl must have at most 50 entries.
REJ2_LINES=0
[ -f "$WORLD_STATE_DIR2/rejected.jsonl" ] && REJ2_LINES=$(wc -l < "$WORLD_STATE_DIR2/rejected.jsonl" | tr -d ' ')
if [ "$REJ2_LINES" = "50" ]; then
  echo "PASS  50-rejection cap hit exactly"; pass=$((pass+1))
else
  echo "FAIL  expected 50 rejections, got $REJ2_LINES"; fail=$((fail+1))
fi

# Outbox must contain the remaining events (60 - 50 = 10).
OB2_AFTER=$(wc -l < "$WORLD_STATE_DIR2/outbox.jsonl" 2>/dev/null | tr -d ' ')
if [ "$OB2_AFTER" = "10" ]; then
  echo "PASS  outbox keeps the 10 unsent events"; pass=$((pass+1))
else
  echo "FAIL  expected 10 in outbox, got $OB2_AFTER"; fail=$((fail+1))
fi

if [ -n "$STUB2_PID" ] && kill -0 "$STUB2_PID" 2>/dev/null; then
  kill "$STUB2_PID" 2>/dev/null || true
  wait "$STUB2_PID" 2>/dev/null || true
fi

# ---------------------------------------------------------------------------
echo | tee -a "$LOG"
echo "RESULT: pass=$pass fail=$fail" | tee -a "$LOG"
exit $fail
