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
# Allow fixture git commits on `main`; the global dev-stack pre-commit hook
# would otherwise block them. Test fixtures build throwaway repos just to
# exercise collectors; their commits have no further reach.
export ALLOW_MAIN_COMMIT=1
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
PROJ_BASE="$(mktemp -d -t proj.XXXXXX)"
mkdir -p "$PROJ_BASE/FashionVerse/specs/_session"
mkdir -p "$PROJ_BASE/FashionVerse-wt/specs/_session"

cat > "$PROJ_BASE/FashionVerse/specs/_session/2026-10-01-tasks.md" <<'EOF'
# Session task log — 2026-10-01
- [x] 09:30 — Write brief ✓ 09:55 [green: outputs ok]
- [x] 10:00 — Plain done
- [ ] 11:00 — Plain pending
- garbage line
EOF
cat > "$PROJ_BASE/FashionVerse-wt/specs/_session/2026-10-01-tasks.md" <<'EOF'
- [x] 09:30 — should NOT count, FashionVerse-wt must be skipped ✓ 09:55 [x]
EOF

# Real collector over a fixture base: one repo dir with a main checkout and a
# `-wt` feature copy beside it.
OUT_TASKS="$(mktemp)"
PYTHONPATH="$ROOT" python3 - "$PROJ_BASE" "$OUT_TASKS" <<'PY' 2>&1 | tee -a "$LOG"
import sys, json, pathlib
import world_push_sources as w
w._SESSION_GLOBS = [pathlib.Path(sys.argv[1])]
events = list(w.collect_session_tasks())
with open(sys.argv[2], 'w') as fh:
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

# jdelegate v2: project from run.sh cd line, stale no-exit -> failed, live pid -> running
JD2="$(mktemp -d -t jd2.XXXXXX)"
JD2_PROJ="$(mktemp -d -t jd2proj.XXXXXX)/Some-Proj"
mkdir -p "$JD2_PROJ"
for n in dead-old live-fresh; do
  mkdir -p "$JD2/2026-10-02T10-00-00-123Z-$n"
  printf '#!/bin/bash\n# jdelegate worker: %s · gpt-6-luna\nset -o pipefail\ncd '"'"'%s'"'"' || exit 1\n' "$n" "$JD2_PROJ" > "$JD2/2026-10-02T10-00-00-123Z-$n/run.sh"
done
echo 999999 > "$JD2/2026-10-02T10-00-00-123Z-dead-old/pid"
touch -t 202601010000 "$JD2/2026-10-02T10-00-00-123Z-dead-old/run.sh"
echo $$ > "$JD2/2026-10-02T10-00-00-123Z-live-fresh/pid"
OUT_JD2="$(PYTHONPATH="$ROOT" python3 - "$JD2" <<'PY' 2>&1
import sys, json, pathlib
import jdelegate_runs
for e in jdelegate_runs.iter_runs(pathlib.Path(sys.argv[1])):
    print(e["title"], "|", e["status"], "|", e["project"], "|", e["id"])
PY
)"
assert_contains "jdelegate cd -> canonical project" "| some-proj |" "$OUT_JD2"
assert_contains "jdelegate dead old pid -> failed (no exit)" "dead-old (no exit) | failed |" "$OUT_JD2"
assert_contains "jdelegate fresh live pid -> running" "live-fresh | running |" "$OUT_JD2"

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
# Accept/truncate is exercised against a real stub server in section 10. Clear
# the queued event here so later sections start from an empty outbox.
rm -f "$WORLD_STATE_DIR/outbox.jsonl"

# ---------------------------------------------------------------------------
echo "## 4) sent-id dedupe" | tee -a "$LOG"
WORLD_STATE_DIR2="$(mktemp -d -t worldsent.XXXXXX)"
WORLD_STATE_DIR="$WORLD_STATE_DIR2" PYTHONPATH="$ROOT" python3 - "$WORLD_STATE_DIR2" <<'PY' 2>&1 | tee -a "$LOG"
import sys, json, pathlib
import lib_world
sd =pathlib.Path(sys.argv[1])
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

echo "## 5b) track add --source/--key" | tee -a "$LOG"
WORLD_STATE_DIR="$WORLD_STATE_DIR" "$TRACK" --dry-run add --kind task --project testproj \
  --status running --title "keyed" --source live --key run:x:running 2>/dev/null > "$WORLD_STATE_DIR/key.out"
EXP_ID="$(printf '%s' 'live:run:x:running' | shasum -a 1 | cut -d' ' -f1)"
assert_contains "--key id = sha1(source:key)" "\"id\":\"$EXP_ID\"" "$(cat "$WORLD_STATE_DIR/key.out")"
assert_contains "--source sets event source" '"source":"live"' "$(cat "$WORLD_STATE_DIR/key.out")"
WORLD_STATE_DIR="$WORLD_STATE_DIR" "$TRACK" --dry-run add --kind task --project testproj \
  --status running --title "nokey" 2>/dev/null > "$WORLD_STATE_DIR/nokey.out"
assert_contains "no flags keeps source track" '"source":"track"' "$(cat "$WORLD_STATE_DIR/nokey.out")"
if grep -Fq "\"id\":\"$EXP_ID\"" "$WORLD_STATE_DIR/nokey.out"; then
  echo "FAIL  no --key id changed"; fail=$((fail+1))
else
  echo "PASS  no --key keeps timestamp-derived id"; pass=$((pass+1))
fi

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
    re.compile(r'xox[abprs]-', re.IGNORECASE),
    re.compile(r'bearer\s+\S+', re.IGNORECASE),
    re.compile(r'[A-Za-z0-9+/=_-]{33,}'),
]

cases = {
    "long_path":   "fixed /Users/mohamed/projects/some-very-long-path-segment-name-here-1234/build",
    "sk_key":      "deploy with sk-abcdefghijklmnopqrstuv to staging",
    "bearer_hdr":  "auth header: Bearer xoxb-1234567890abcdefghij token here",
    "normal":      "ran tests ok",
    "slack_bot":   "posted with " + "xox" + "b-1234-5678-abcdefXYZ" + " to #ops",
    "slack_user":  "XOX" + "P-99-abc in a title",
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
echo "## 11) canonical_project resolves worktrees to base repo" | tee -a "$LOG"
# Build a temp "base repo" with a linked worktree, then verify both map to the
# same canonical project slug.
CANON_BASE="$(mktemp -d -t canonbase.XXXXXX)"
mkdir -p "$CANON_BASE/repos/FashionVerse"
cd "$CANON_BASE/repos/FashionVerse" && git init -q -b main . >/dev/null
# Need an initial commit so worktrees can be added.
git -C "$CANON_BASE/repos/FashionVerse" -c user.name=t -c user.email=t@t \
  commit --allow-empty -q -m init >/dev/null
# Add a worktree under FashionVerse-g-pricing — uses git's worktree machinery so
# rev-parse --git-common-dir returns the main repo's .git.
git -C "$CANON_BASE/repos/FashionVerse" worktree add -q -b feat \
  "$CANON_BASE/repos/FashionVerse-g-pricing" >/dev/null

# Sanity: git-common-dir on the worktree should point at the main repo.
COMMON_DIR="$(git -C "$CANON_BASE/repos/FashionVerse-g-pricing" rev-parse --path-format=absolute --git-common-dir 2>/dev/null)"
assert_contains "git-common-dir points to base repo" "/FashionVerse/.git" "$COMMON_DIR"

CANON_OUT="$(PYTHONPATH="$ROOT" python3 - "$CANON_BASE" <<'PY' 2>&1
import sys, pathlib
import lib_world
base = pathlib.Path(sys.argv[1])
main = base / "repos" / "FashionVerse"
wt   = base / "repos" / "FashionVerse-g-pricing"
print("MAIN=" + lib_world.canonical_project(main))
print("WT="   + lib_world.canonical_project(wt))
# Also exercise a non-git dir → falls back to dir name slug.
plain = base / "repos" / "Some Cool Project"
print("PLAIN=" + lib_world.canonical_project(plain))
# Truly missing path: the *input* is empty/None.
print("NONE=" + lib_world.canonical_project(None))
print("EMPTY=" + lib_world.canonical_project(""))
PY
)"
assert_contains "canonical_project: main FashionVerse -> fashionverse" "MAIN=fashionverse" "$CANON_OUT"
assert_contains "canonical_project: worktree -> fashionverse" "WT=fashionverse" "$CANON_OUT"
assert_contains "canonical_project: non-git dir falls back to slug" "PLAIN=some-cool-project" "$CANON_OUT"
assert_contains "canonical_project: None is 'unknown'" "NONE=unknown" "$CANON_OUT"
assert_contains "canonical_project: empty string is 'unknown'" "EMPTY=unknown" "$CANON_OUT"

# ---------------------------------------------------------------------------
echo "## 12) session-tasks collector canonicalises the project" | tee -a "$LOG"
# Build a base repo with a worktree; drop a -tasks.md in BOTH the main
# checkout and the worktree. The collector must emit from each logical file
# ONCE: only the main-checkout copy is read (the worktree copy is skipped).
# The project on every emitted event must be the canonical 'fashionverse'.
TASKS_BASE="$(mktemp -d -t tasksbase.XXXXXX)"
mkdir -p "$TASKS_BASE/FashionVerse"
cd "$TASKS_BASE/FashionVerse" && git init -q -b main . >/dev/null
git -C "$TASKS_BASE/FashionVerse" -c user.name=t -c user.email=t@t \
  commit --allow-empty -q -m init >/dev/null
git -C "$TASKS_BASE/FashionVerse" worktree add -q -b feat \
  "$TASKS_BASE/FashionVerse-g-pricing" >/dev/null
mkdir -p "$TASKS_BASE/FashionVerse-g-pricing/specs/_session"
cat > "$TASKS_BASE/FashionVerse-g-pricing/specs/_session/2026-10-05-tasks.md" <<'EOF'
# Session task log — 2026-10-05
- [x] 09:30 — Canonical test ✓ 09:55 [green: passes]
- [ ] 10:00 — Pending canonical
EOF
# Main checkout also has a tasks file. Collector should emit from THIS one
# only — the worktree copy is skipped.
mkdir -p "$TASKS_BASE/FashionVerse/specs/_session"
cat > "$TASKS_BASE/FashionVerse/specs/_session/2026-10-06-tasks.md" <<'EOF'
# Session task log — 2026-10-06
- [x] 09:30 — Main repo task ✓ 09:55 [green: ok]
EOF

TASKS_OUT="$(PYTHONPATH="$ROOT" python3 - "$TASKS_BASE" <<'PY' 2>&1
import sys, json, pathlib
import world_push_sources as w
import pathlib
w._SESSION_GLOBS = [pathlib.Path(sys.argv[1])]
events = list(w.collect_session_tasks())
for e in events:
    print(json.dumps(e))
PY
)"
assert_contains "session-tasks: main-checkout task -> project=fashionverse" '"project": "fashionverse"' "$TASKS_OUT"
assert_contains "session-tasks: main-checkout task has correct title" "Main repo task" "$TASKS_OUT"
# Worktree copy must NOT be emitted.
if printf '%s' "$TASKS_OUT" | grep -Fq "Canonical test"; then
  echo "FAIL  worktree copy of session-tasks leaked"; fail=$((fail+1))
else
  echo "PASS  worktree copy of session-tasks skipped"; pass=$((pass+1))
fi
# Count distinct projects — must be 1.
DISTINCT_PROJ="$(printf '%s\n' "$TASKS_OUT" | PYTHONPATH="$ROOT" python3 -c '
import json, sys
ps = set()
for ln in sys.stdin:
    ln = ln.strip()
    if not ln: continue
    ps.add(json.loads(ln)["project"])
print(",".join(sorted(ps)))
')"
assert_eq "session-tasks: only one distinct project across main+worktree" "fashionverse" "$DISTINCT_PROJ"

# ---------------------------------------------------------------------------
echo "## 13) spec-kit collector canonicalises the project" | tee -a "$LOG"
# Two-orbiter scenario: a real git repo with a worktree. Spec-kit must read
# the spec files from the MAIN checkout only; the worktree copies are
# skipped. Project must equal the canonical main repo slug.
SPEC_BASE2="$(mktemp -d -t specbase2.XXXXXX)"
mkdir -p "$SPEC_BASE2/FashionVerse"
cd "$SPEC_BASE2/FashionVerse" && git init -q -b main . >/dev/null
git -C "$SPEC_BASE2/FashionVerse" -c user.name=t -c user.email=t@t \
  commit --allow-empty -q -m init >/dev/null
git -C "$SPEC_BASE2/FashionVerse" worktree add -q -b feat \
  "$SPEC_BASE2/FashionVerse-g-pricing" >/dev/null
mkdir -p "$SPEC_BASE2/FashionVerse/specs/001-x"
mkdir -p "$SPEC_BASE2/FashionVerse-g-pricing/specs/001-x"
cat > "$SPEC_BASE2/FashionVerse/specs/001-x/tasks.md" <<'EOF'
# Spec 001-x
- [x] step one
- [ ] step two
EOF
cat > "$SPEC_BASE2/FashionVerse-g-pricing/specs/001-x/tasks.md" <<'EOF'
# Spec 001-x (worktree copy)
- [x] step one
- [ ] step two
EOF
# Second repo: EDUNEX main + edunex-056-rewards worktree (no main spec file).
SPEC_BASE3="$(mktemp -d -t specbase3.XXXXXX)"
mkdir -p "$SPEC_BASE3/EDUNEX_GOLDEN_MASTER_v1.0.0"
cd "$SPEC_BASE3/EDUNEX_GOLDEN_MASTER_v1.0.0" && git init -q -b main . >/dev/null
git -C "$SPEC_BASE3/EDUNEX_GOLDEN_MASTER_v1.0.0" -c user.name=t -c user.email=t@t \
  commit --allow-empty -q -m init >/dev/null
git -C "$SPEC_BASE3/EDUNEX_GOLDEN_MASTER_v1.0.0" worktree add -q -b feat \
  "$SPEC_BASE3/edunex-056-rewards" >/dev/null
mkdir -p "$SPEC_BASE3/EDUNEX_GOLDEN_MASTER_v1.0.0/specs/002-y"
mkdir -p "$SPEC_BASE3/edunex-056-rewards/specs/002-y"
cat > "$SPEC_BASE3/EDUNEX_GOLDEN_MASTER_v1.0.0/specs/002-y/tasks.md" <<'EOF'
# Spec 002-y
- [x] only step
EOF
cat > "$SPEC_BASE3/edunex-056-rewards/specs/002-y/tasks.md" <<'EOF'
# Spec 002-y (worktree copy)
- [x] only step
EOF

SPEC_OUT="$(PYTHONPATH="$ROOT" python3 - "$SPEC_BASE2" "$SPEC_BASE3" <<'PY' 2>&1
import sys, json, pathlib
import world_push_sources as w
import pathlib
w._SESSION_GLOBS = [pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])]
events = list(w.collect_specs())
for e in events:
    print(json.dumps(e))
PY
)"
assert_contains "spec-kit: FashionVerse main -> fashionverse" '"project": "fashionverse"' "$SPEC_OUT"
assert_contains "spec-kit: edunex main -> edunex-golden-master-v1-0-0" '"project": "edunex-golden-master-v1-0-0"' "$SPEC_OUT"
# Worktree copies must be skipped.
SPEC_WORKTREE_LEAK="$(printf '%s' "$SPEC_OUT" | grep -c 'worktree copy' || true)"
assert_eq "spec-kit: worktree copy was skipped" "0" "$SPEC_WORKTREE_LEAK"

# ---------------------------------------------------------------------------
echo "## 14) git collector canonicalises per-repo project" | tee -a "$LOG"
# Build a fresh state dir + a single worktree repo.
GIT_BASE="$(mktemp -d -t gitbase.XXXXXX)"
mkdir -p "$GIT_BASE/FashionVerse"
cd "$GIT_BASE/FashionVerse" && git init -q -b main . >/dev/null
git -C "$GIT_BASE/FashionVerse" -c user.name=t -c user.email=t@t \
  commit --allow-empty -q -m init >/dev/null
git -C "$GIT_BASE/FashionVerse" worktree add -q -b feat \
  "$GIT_BASE/FashionVerse-g-pricing" >/dev/null
git -C "$GIT_BASE/FashionVerse-g-pricing" -c user.name=t -c user.email=t@t \
  commit --allow-empty -q -m "feature commit" >/dev/null

GIT_STATE="$(mktemp -d -t gitstate.XXXXXX)"
GIT_OUT="$(PYTHONPATH="$ROOT" python3 - "$GIT_BASE" "$GIT_STATE" <<'PY' 2>&1
import sys, json, pathlib, os
import world_push_sources as w
import lib_world
base = pathlib.Path(sys.argv[1])
os.environ["WORLD_STATE_DIR"] = sys.argv[2]
# Use isolated state + iterate just the repos under base.
events = list(w.collect_git(roots=[base]))
for e in events:
    print(json.dumps(e))
PY
)"
# The worktree IS its own git root (it has a .git file pointing back). Since
# it should be EXCLUDED by looks_like_worktree, only the main repo should emit.
DISTINCT_GIT_PROJ="$(printf '%s\n' "$GIT_OUT" | PYTHONPATH="$ROOT" python3 -c '
import json, sys
ps = set()
for ln in sys.stdin:
    ln = ln.strip()
    if not ln: continue
    ps.add(json.loads(ln)["project"])
print(",".join(sorted(ps)))
')"
assert_contains "git: project=fashionverse" "fashionverse" "$DISTINCT_GIT_PROJ"
# Crucially: it must NOT emit 'fashionverse-g-pricing' as a project (worktree
# must be excluded at the iter_git_roots layer).
if printf '%s\n' "$GIT_OUT" | grep -Fq '"project": "fashionverse-g-pricing"'; then
  echo "FAIL  git collector emitted worktree as its own project"; fail=$((fail+1))
else
  echo "PASS  git collector excluded worktree from emission"; pass=$((pass+1))
fi

# ---------------------------------------------------------------------------
echo "## 15) herdr: project from cwd is canonicalised" | tee -a "$LOG"
HERDR_STATE="$(mktemp -d -t herdrstate.XXXXXX)"
HERDR_OUT="$(PYTHONPATH="$ROOT" python3 - "$HERDR_STATE" "$TASKS_BASE" <<'PY' 2>&1
import sys, json, pathlib, os
import world_push_sources as w
import lib_world
os.environ["WORLD_STATE_DIR"] = sys.argv[1]
# Patch herdr to a controlled subprocess that emits a known JSON payload.
bin_dir = pathlib.Path(sys.argv[1]) / "bin"
bin_dir.mkdir(parents=True, exist_ok=True)
fake = bin_dir / "herdr"
fake.write_text("#!/bin/sh\necho '{\"result\":{\"panes\":[{\"pane_id\":\"p1\",\"terminal_title_stripped\":\"t\",\"cwd\":\"%s\",\"agent\":\"claude\"}]}}'\n" % (sys.argv[2] + "/FashionVerse-g-pricing"))
fake.chmod(0o755)
os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ.get("PATH","")
events = list(w.collect_herdr())
for e in events:
    print(json.dumps(e))
PY
)"
assert_contains "herdr: cwd in worktree -> project=fashionverse" '"project": "fashionverse"' "$HERDR_OUT"

# ---------------------------------------------------------------------------
echo "## 16) jdelegate: cwd-derived project is canonicalised" | tee -a "$LOG"
# jdelegate_runs doesn't itself key on cwd today, so this verifies the
# canonicalisation helper is wired in for paths the collector does see
# (e.g. via run.sh). Here we sanity-check the helper alone, since the
# collector doesn't take a cwd per-run yet.
JD_CANON_OUT="$(PYTHONPATH="$ROOT" python3 - "$TASKS_BASE" <<'PY' 2>&1
import sys, pathlib
import lib_world
base = pathlib.Path(sys.argv[1])
print("WT=" + lib_world.canonical_project(base / "FashionVerse-g-pricing"))
print("MAIN=" + lib_world.canonical_project(base / "FashionVerse"))
PY
)"
assert_contains "jdelegate helper: worktree cwd -> fashionverse" "WT=fashionverse" "$JD_CANON_OUT"
assert_contains "jdelegate helper: main repo -> fashionverse" "MAIN=fashionverse" "$JD_CANON_OUT"

# ---------------------------------------------------------------------------
echo "## 17) claude-sessions: project from transcript folder is canonicalised" | tee -a "$LOG"
CS_BASE="$(mktemp -d -t csbase.XXXXXX)"
# Build a tree mimicking ~/.claude/projects for a worktree-derived project.
# The collector walks $HOME/.claude/projects/<encoded-folder>/*.jsonl.
mkdir -p "$CS_BASE/.claude/projects/-Users-mohamedbardouni-projects-FashionVerse-g-pricing"
mkdir -p "$CS_BASE/.claude/projects/-Users-mohamedbardouni-projects-FashionVerse"
mkdir -p "$CS_BASE/.claude/projects/-Users-mohamedbardouni-projects-beldify"
mkdir -p "$CS_BASE/.claude/projects/-Users-mohamedbardouni"  # home-level (no projects segment)
mkdir -p "$CS_BASE/.claude/projects/-tmp-scratch"
# Need a real FashionVerse base repo under the fake $HOME/projects so
# canonical_project resolves FashionVerse-g-pricing -> fashionverse.
mkdir -p "$CS_BASE/projects/FashionVerse"
(cd "$CS_BASE/projects/FashionVerse" && git init -q -b main .) >/dev/null
git -C "$CS_BASE/projects/FashionVerse" -c user.name=t -c user.email=t@t \
  commit --allow-empty -q -m init >/dev/null
git -C "$CS_BASE/projects/FashionVerse" worktree add -q -b feat \
  "$CS_BASE/projects/FashionVerse-g-pricing" >/dev/null
# Drop one transcript file in each dir, all touched 'now'.
touch "$CS_BASE/.claude/projects/-Users-mohamedbardouni-projects-FashionVerse-g-pricing/sess1.jsonl"
touch "$CS_BASE/.claude/projects/-Users-mohamedbardouni-projects-FashionVerse/sess2.jsonl"
touch "$CS_BASE/.claude/projects/-Users-mohamedbardouni-projects-beldify/sess3.jsonl"
touch "$CS_BASE/.claude/projects/-Users-mohamedbardouni/sess4.jsonl"
touch "$CS_BASE/.claude/projects/-tmp-scratch/sess5.jsonl"

CS_OUT="$(PYTHONPATH="$ROOT" HOME="$CS_BASE" python3 - <<'PY' 2>&1
import sys, json, pathlib, os
import world_push_sources as w
events = list(w.collect_transcripts())
for e in events:
    print(json.dumps(e))
PY
)"
# Every FashionVerse-g-pricing transcript must collapse into project='fashionverse'.
assert_contains "claude-sessions: worktree folder -> fashionverse" "fashionverse" "$CS_OUT"
# beldify stays 'beldify' (not a worktree).
assert_contains "claude-sessions: non-worktree folder -> beldify" "beldify" "$CS_OUT"
# Home-level folder (no projects segment) must be 'me' under new rule.
assert_contains "claude-sessions: home-level folder -> me" "me 2 transcript files" "$CS_OUT"

# ---------------------------------------------------------------------------
echo "## 18) skill-use collector: incremental, one event per (skill,project,day)" | tee -a "$LOG"
SK_BASE="$(mktemp -d -t skbase.XXXXXX)"
SK_STATE="$(mktemp -d -t skstate.XXXXXX)"
# Fake a transcript dir + a single .jsonl with several Skill tool_use blocks.
TX_DIR="$SK_BASE/.claude/projects/-Users-mohamedbardouni-projects-beldify"
mkdir -p "$TX_DIR"
cat > "$TX_DIR/2026-01-01.jsonl" <<'EOF'
{"role":"user","content":"hi"}
{"role":"assistant","content":[{"type":"tool_use","name":"Skill","input":{"skill":"kb-spec"}},{"type":"text","text":"ok"}]}
{"role":"user","content":"go"}
{"role":"assistant","content":[{"type":"tool_use","name":"Skill","input":{"skill":"kb-spec"}},{"type":"text","text":"ok"}]}
{"role":"assistant","content":[{"type":"tool_use","name":"Skill","input":{"skill":"cso"}},{"type":"text","text":"ok"}]}
{"role":"user","content":"now kb-spec again"}
{"role":"assistant","content":[{"type":"tool_use","name":"Skill","input":{"skill":"kb-spec"}},{"type":"text","text":"ok"}]}
EOF
# Touch an older transcript that is OUTSIDE the 90-day window — should be
# skipped on first run. (mtime back-dated via utimes.)
TX_OLD="$SK_BASE/.claude/projects/-Users-mohamedbardouni-projects-beldify/2024-01-01.jsonl"
echo '{"role":"assistant","content":[{"type":"tool_use","name":"Skill","input":{"skill":"old-skill"}}]}' > "$TX_OLD"
touch -t 202401011200 "$TX_OLD" 2>/dev/null || true

SK_OUT="$(PYTHONPATH="$ROOT" HOME="$SK_BASE" WORLD_STATE_DIR="$SK_STATE" python3 - <<'PY' 2>&1
import sys, json, pathlib
import world_push_sources as w
events = list(w.collect_skill_use())
w.commit_state()  # cursor is only persisted after a successful send
for e in events:
    print(json.dumps(e))
PY
)"
# Project must be 'beldify' (canonicalised from folder name).
assert_contains "skill-use: project= beldify" '"project": "beldify"' "$SK_OUT"
# One event per (skill, project, day). 3 kb-spec + 1 cso on 2026-01-01 -> 2 events.
COUNT_KB_SPEC="$(printf '%s\n' "$SK_OUT" | grep -F '"skill"' | grep -F 'kb-spec' | grep -c 'kb-spec used' || true)"
COUNT_CSO="$(printf '%s\n' "$SK_OUT" | grep -F '"cso"' | grep -c 'cso used' || true)"
# Count actual emitted events (one per (skill,project,day) line).
EMITTED="$(printf '%s\n' "$SK_OUT" | grep -c '"source": "skill-use"' || true)"
assert_eq "skill-use: 2 unique (skill,project,day) events" "2" "$EMITTED"
# Title for kb-spec should report '3x'.
KB_TITLE="$(printf '%s\n' "$SK_OUT" | grep -F 'kb-spec' | head -1 | python3 -c 'import json,sys; print(json.loads(sys.stdin.read())["title"])' 2>/dev/null || true)"
assert_contains "skill-use: kb-spec count in title" "3x" "$KB_TITLE"
# Old transcript (mtime > 90d) should NOT contribute on first run.
if printf '%s\n' "$SK_OUT" | grep -Fq "old-skill"; then
  echo "FAIL  skill-use: stale transcript (>90d) was read on first run"; fail=$((fail+1))
else
  echo "PASS  skill-use: stale transcript skipped on first run"; pass=$((pass+1))
fi

# State file must exist now and remember the offset of the file we scanned.
CURSOR_FILE="$SK_STATE/skill-scan.json"
if [ -f "$CURSOR_FILE" ]; then
  CURSOR_CONTENT="$(cat "$CURSOR_FILE")"
  assert_contains "skill-use: cursor file remembers scanned file size" "size" "$CURSOR_CONTENT"
  # A second run with the same transcript should be a no-op (offset = size).
  SK_OUT2="$(PYTHONPATH="$ROOT" HOME="$SK_BASE" WORLD_STATE_DIR="$SK_STATE" python3 - <<'PY' 2>&1
import sys, json, pathlib
import world_push_sources as w
events = list(w.collect_skill_use())
for e in events:
    print(json.dumps(e))
PY
)"
  EMITTED2="$(printf '%s\n' "$SK_OUT2" | grep -c '"source": "skill-use"' || true)"
  assert_eq "skill-use: second run is a no-op (offset = size)" "0" "$EMITTED2"
else
  echo "FAIL  skill-use: cursor file not written"; fail=$((fail+1))
fi

# ---------------------------------------------------------------------------
echo "## 19) gh-prs: dedupe author + reviewed-by, project canonicalised" | tee -a "$LOG"
# Stub `gh` in PATH and have it emit one author PR + one reviewed-by PR.
GH_STUB_DIR="$(mktemp -d -t ghstub.XXXXXX)"
GH_STATE="$(mktemp -d -t ghstate.XXXXXX)"
cat > "$GH_STUB_DIR/gh" <<'EOF'
#!/bin/sh
# Return 2 PRs — one authored, one reviewed, in different repos (worktree-style
# "feature/FashionVerse-g-pricing" repo name should canonicalise to 'fashionverse').
cat <<JSON
[
  {"number":1,"title":"authored in FashionVerse-g-pricing","state":"open","repository":{"nameWithOwner":"me/FashionVerse-g-pricing"},"url":"u1","createdAt":"2026-01-01T00:00:00Z","closedAt":null},
  {"number":2,"title":"reviewed in FashionVerse-p2-gateway","state":"merged","repository":{"nameWithOwner":"me/FashionVerse-p2-gateway"},"url":"u2","createdAt":"2026-01-02T00:00:00Z","closedAt":"2026-01-03T00:00:00Z"},
  {"number":3,"title":"reviewed in FashionVerse-p2-gateway","state":"open","repository":{"nameWithOwner":"me/FashionVerse-p2-gateway"},"url":"u3","createdAt":"2026-01-04T00:00:00Z","closedAt":null}
]
JSON
EOF
chmod +x "$GH_STUB_DIR/gh"

GH_OUT="$(PYTHONPATH="$ROOT" PATH="$GH_STUB_DIR:$PATH" WORLD_STATE_DIR="$GH_STATE" python3 - <<'PY' 2>&1
import sys, json, pathlib
import world_push_sources as w
# First call: full discovery (author + reviewed-by, both stubbed). Deduped by
# (repo, number) so PR #2 and #3 (both reviewed in the same repo) stay distinct.
events_first = list(w.collect_prs())
print("# first=" + str(len(events_first)))
for e in events_first:
    print(json.dumps(e))
PY
)"
assert_contains "gh-prs: author + reviewed PR both emitted" "fashionverse" "$GH_OUT"
# Local dedupe: PR #2 + #3 are both in me/FashionVerse-p2-gateway with different
# numbers — we expect 3 unique events (1 authored, 2 reviewed), not 4.
if printf '%s' "$GH_OUT" | grep -q 'first=3'; then
  echo "PASS  gh-prs: local dedupe of author+reviewed yielded 3 unique"; pass=$((pass+1))
else
  echo "FAIL  gh-prs: local dedupe of author+reviewed wrong; first line: $(printf '%s' "$GH_OUT" | head -1)"; fail=$((fail+1))
fi

# Hourly cache: write a fresh timestamp (now) to the state file, then re-call.
# collect_prs reads the cache on entry, so the second call should be empty.
GH_OUT2="$(PYTHONPATH="$ROOT" PATH="$GH_STUB_DIR:$PATH" WORLD_STATE_DIR="$GH_STATE" python3 - <<'PY' 2>&1
import sys, json, pathlib, time
import world_push_sources as w
# Write the cache as if commit_state() had just been called.
import os
state = pathlib.Path(os.environ["WORLD_STATE_DIR"])
(state / "gh-prs.ts").write_text(str(int(time.time())))
events_cached = list(w.collect_prs())
print("# cached=" + str(len(events_cached)))
PY
)"
if printf '%s' "$GH_OUT2" | grep -q 'cached=0'; then
  echo "PASS  gh-prs: hourly cache hit on second call"; pass=$((pass+1))
else
  echo "FAIL  gh-prs: hourly cache did not hit; got: $(printf '%s' "$GH_OUT2" | head -1)"; fail=$((fail+1))
fi

# ---------------------------------------------------------------------------
echo "## 20) REGRESSION: git collector emits each sha once across worktrees" | tee -a "$LOG"
# Two git worktrees of the same repo share commits. The collector must run
# `git log` ONCE per git-common-dir so each SHA is seen exactly once.
WT_GIT_BASE="$(mktemp -d -t wtgit.XXXXXX)"
WT_GIT_STATE="$(mktemp -d -t wtgitstate.XXXXXX)"
mkdir -p "$WT_GIT_BASE/FashionVerse"
(cd "$WT_GIT_BASE/FashionVerse" && git init -q -b main .) >/dev/null
git -C "$WT_GIT_BASE/FashionVerse" -c user.name=t -c user.email=t@t \
  commit --allow-empty -q -m init >/dev/null
git -C "$WT_GIT_BASE/FashionVerse" -c user.name=t -c user.email=t@t \
  commit --allow-empty -q -m "second commit" >/dev/null
git -C "$WT_GIT_BASE/FashionVerse" worktree add -q -b feat \
  "$WT_GIT_BASE/FashionVerse-g-pricing" >/dev/null
git -C "$WT_GIT_BASE/FashionVerse-g-pricing" -c user.name=t -c user.email=t@t \
  commit --allow-empty -q -m "feature commit" >/dev/null

WT_GIT_OUT="$(WORLD_STATE_DIR="$WT_GIT_STATE" PYTHONPATH="$ROOT" _WORLD_ROOTS="$WT_GIT_BASE" python3 - <<'PY' 2>&1
import sys, json, os, pathlib
import world_push_sources as w
roots = [pathlib.Path(p) for p in os.environ["_WORLD_ROOTS"].split(os.pathsep)]
events = list(w.collect_git(roots=roots))
# Persist the per-repo HEAD cursor so we can verify the state file path.
w.commit_state()
print("# events=" + str(len(events)))
seen_shas = []
seen_ids = []
seen_projects = []
for e in events:
    seen_shas.append(e["ref"])
    seen_ids.append(e["id"])
    seen_projects.append(e["project"])
print("# shas=" + ",".join(seen_shas))
print("# ids=" + ",".join(seen_ids))
print("# projects=" + ",".join(sorted(set(seen_projects))))
print("# duplicates=" + str(len(seen_shas) - len(set(seen_shas))))
PY
)"

echo "$WT_GIT_OUT" | tee -a "$LOG" >/dev/null
# Each unique sha emitted once, even though there are two worktrees.
DUPES="$(printf '%s' "$WT_GIT_OUT" | python3 -c '
import sys
for ln in sys.stdin:
    if ln.startswith("# duplicates="):
        print(ln.split("=", 1)[1].strip())
        break
')"
WT_EVENTS="$(printf '%s' "$WT_GIT_OUT" | python3 -c '
import sys
for ln in sys.stdin:
    if ln.startswith("# events="):
        print(ln.split("=", 1)[1].strip())
        break
')"
assert_eq "git: no duplicate shas across worktrees" "0" "$DUPES"
# ID uniqueness: every emitted event must have a unique id. Compare the
# emitted event count to the deduped id count.
assert "git: emitted events > 0" [ "${WT_EVENTS:-0}" -gt 0 ]
if [ "${WT_EVENTS:-0}" -gt 0 ] 2>/dev/null; then
  WT_IDS="$(printf '%s' "$WT_GIT_OUT" | python3 -c '
import sys
for ln in sys.stdin:
    if ln.startswith("# ids="):
        print(ln.split("=", 1)[1].strip())
        break
')"
  WT_IDS_DEDUP="$(printf '%s' "$WT_IDS" | tr ',' '\n' | awk 'NF' | sort -u | wc -l | tr -d ' ')"
  assert_eq "git: unique id count == total emitted count" "$WT_EVENTS" "$WT_IDS_DEDUP"
fi

# All projects must be a single canonical project (fashionverse). The git root
# key in `git.<slug>.sha` is the COMMON-DIR state, not the worktree's path.
WT_PROJECTS="$(printf '%s' "$WT_GIT_OUT" | python3 -c '
import sys
for ln in sys.stdin:
    if ln.startswith("# projects="):
        print(ln.split("=", 1)[1].strip())
        break
')"
assert_eq "git: only one canonical project across worktrees" "fashionverse" "$WT_PROJECTS"

# The git state file MUST be keyed by git-common-dir's parent (fashionverse),
# not by fashionverse-g-pricing (which would be the worktree dir).
SHA_STATE="$(ls "$WT_GIT_STATE"/git.*.sha 2>/dev/null | head -1)"
if [ -n "$SHA_STATE" ] && printf '%s' "$SHA_STATE" | grep -Eq 'git\.fashionverse-g-pricing\.sha'; then
  echo "FAIL  git state file keyed by worktree dir (not canonical)"; fail=$((fail+1))
elif [ -n "$SHA_STATE" ]; then
  echo "PASS  git state file keyed by canonical main repo dir"; pass=$((pass+1))
else
  echo "FAIL  git state file missing"; fail=$((fail+1))
fi

# ---------------------------------------------------------------------------
echo "## 21) REGRESSION: session-tasks + spec-kit skip worktree copies once" | tee -a "$LOG"
# Build a repo with a SECOND git worktree (FashionVerse-g-pricing) and drop the
# SAME specs/_session/tasks.md under both. The collector must emit each task
# line EXACTLY ONCE (from the main checkout) — even though its current
# looks_like_worktree helper doesn't match FashionVerse-g-pricing.
TWT_BASE="$(mktemp -d -t twt.XXXXXX)"
mkdir -p "$TWT_BASE/FashionVerse"
(cd "$TWT_BASE/FashionVerse" && git init -q -b main .) >/dev/null
git -C "$TWT_BASE/FashionVerse" -c user.name=t -c user.email=t@t \
  commit --allow-empty -q -m init >/dev/null
git -C "$TWT_BASE/FashionVerse" worktree add -q -b feat \
  "$TWT_BASE/FashionVerse-g-pricing" >/dev/null

# Drop a -tasks.md in the MAIN worktree's specs/_session/ and an identical
# copy in the WORKTREE. The collector must read both but emit each line ONCE.
mkdir -p "$TWT_BASE/FashionVerse/specs/_session"
mkdir -p "$TWT_BASE/FashionVerse-g-pricing/specs/_session"
cat > "$TWT_BASE/FashionVerse/specs/_session/2026-10-09-tasks.md" <<'EOF'
# Session task log — 2026-10-09
- [x] 09:30 — Two-worktree regression ✓ 09:55 [green: passes]
- [ ] 10:00 — Two-worktree pending
EOF
cp "$TWT_BASE/FashionVerse/specs/_session/2026-10-09-tasks.md" \
   "$TWT_BASE/FashionVerse-g-pricing/specs/_session/2026-10-09-tasks.md"

TWT_SESS="$(PYTHONPATH="$ROOT" _WORLD_ROOTS="$TWT_BASE" python3 - <<'PY' 2>&1
import sys, json, pathlib, os
import world_push_sources as w
w._SESSION_GLOBS = [pathlib.Path(p) for p in os.environ["_WORLD_ROOTS"].split(os.pathsep)]
events = list(w.collect_session_tasks())
for e in events:
    print(json.dumps(e))
PY
)"
TWT_COUNT="$(printf '%s\n' "$TWT_SESS" | grep -c '"source": "session-tasks"' || true)"
# Two lines parse from the file (the session_tasks parser emits at most 2 events
# — one done + one pending). Per the brief, "lines emitted once": we want 2,
# not 4. Either copy would emit 2 lines; the dedupe must collapse them to 2.
assert_eq "session-tasks: lines emitted once across worktree copies" "2" "$TWT_COUNT"
TWT_PROJS="$(printf '%s\n' "$TWT_SESS" | python3 -c '
import json, sys
ps = set()
for ln in sys.stdin:
    ln = ln.strip()
    if not ln: continue
    ps.add(json.loads(ln)["project"])
print(",".join(sorted(ps)))
')"
assert_eq "session-tasks: project=fashionverse (not -g-pricing)" "fashionverse" "$TWT_PROJS"

# Spec-kit: same idea. Drop the same specs/001-x/tasks.md under both
# worktrees; spec-kit must emit ONE event per file (not two).
mkdir -p "$TWT_BASE/FashionVerse/specs/001-x"
mkdir -p "$TWT_BASE/FashionVerse-g-pricing/specs/001-x"
cat > "$TWT_BASE/FashionVerse/specs/001-x/tasks.md" <<'EOF'
# Spec 001-x
- [x] only step
- [x] second step
EOF
cp "$TWT_BASE/FashionVerse/specs/001-x/tasks.md" \
   "$TWT_BASE/FashionVerse-g-pricing/specs/001-x/tasks.md"

TWT_SPEC="$(PYTHONPATH="$ROOT" _WORLD_ROOTS="$TWT_BASE" python3 - <<'PY' 2>&1
import sys, json, pathlib, os
import world_push_sources as w
w._SESSION_GLOBS = [pathlib.Path(p) for p in os.environ["_WORLD_ROOTS"].split(os.pathsep)]
events = list(w.collect_specs())
for e in events:
    print(json.dumps(e))
PY
)"
TWT_SPEC_COUNT="$(printf '%s\n' "$TWT_SPEC" | grep -c '"source": "spec-kit"' || true)"
assert_eq "spec-kit: one event per spec file across worktree copies" "1" "$TWT_SPEC_COUNT"
TWT_SPEC_PROJ="$(printf '%s\n' "$TWT_SPEC" | python3 -c '
import json, sys
for ln in sys.stdin:
    ln = ln.strip()
    if not ln: continue
    print(json.loads(ln)["project"]); break
')"
assert_eq "spec-kit: project=fashionverse (not -g-pricing)" "fashionverse" "$TWT_SPEC_PROJ"

# ---------------------------------------------------------------------------
echo "## 22) REGRESSION: transcripts project is the canonical folder, not 'claude-sessions'" | tee -a "$LOG"
# The collect_transcripts events must have project = the canonical project
# derived from the transcript folder name; they MUST NEVER have
# project='claude-sessions' (that string belongs to the `source` field).
T_PROJ_BASE="$(mktemp -d -t tproj.XXXXXX)"
mkdir -p "$T_PROJ_BASE/.claude/projects/-Users-mohamedbardouni-projects-FashionVerse-g-pricing"
mkdir -p "$T_PROJ_BASE/.claude/projects/-Users-mohamedbardouni-projects-FashionVerse"
mkdir -p "$T_PROJ_BASE/.claude/projects/-Users-mohamedbardouni"
mkdir -p "$T_PROJ_BASE/projects/FashionVerse"
(cd "$T_PROJ_BASE/projects/FashionVerse" && git init -q -b main .) >/dev/null
git -C "$T_PROJ_BASE/projects/FashionVerse" -c user.name=t -c user.email=t@t \
  commit --allow-empty -q -m init >/dev/null
git -C "$T_PROJ_BASE/projects/FashionVerse" worktree add -q -b feat \
  "$T_PROJ_BASE/projects/FashionVerse-g-pricing" >/dev/null
touch "$T_PROJ_BASE/.claude/projects/-Users-mohamedbardouni-projects-FashionVerse-g-pricing/sess1.jsonl"
touch "$T_PROJ_BASE/.claude/projects/-Users-mohamedbardouni-projects-FashionVerse/sess2.jsonl"
touch "$T_PROJ_BASE/.claude/projects/-Users-mohamedbardouni/sess3.jsonl"

T_PROJ_OUT="$(PYTHONPATH="$ROOT" HOME="$T_PROJ_BASE" python3 - <<'PY' 2>&1
import sys, json, pathlib
import world_push_sources as w
events = list(w.collect_transcripts())
for e in events:
    print(json.dumps(e))
PY
)"
# No event must carry project='claude-sessions'.
if printf '%s\n' "$T_PROJ_OUT" | grep -Fq '"project": "claude-sessions"'; then
  echo "FAIL  transcripts project leaked literal 'claude-sessions'"; fail=$((fail+1))
else
  echo "PASS  transcripts project is never 'claude-sessions'"; pass=$((pass+1))
fi
# Each event must carry project = the canonical folder-derived slug (or 'me').
assert_contains "transcripts: worktree folder -> project=fashionverse" \
  '"project": "fashionverse"' "$T_PROJ_OUT"
assert_contains "transcripts: home-level folder -> project=me" \
  '"project": "me"' "$T_PROJ_OUT"

# ---------------------------------------------------------------------------
echo | tee -a "$LOG"
echo "RESULT: pass=$pass fail=$fail" | tee -a "$LOG"
exit $fail
