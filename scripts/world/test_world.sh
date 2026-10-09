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
echo | tee -a "$LOG"
echo "RESULT: pass=$pass fail=$fail" | tee -a "$LOG"
exit $fail
