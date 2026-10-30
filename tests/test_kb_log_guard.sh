#!/bin/bash
# bash tests/test_kb_log_guard.sh — hooks/kb-log-guard.sh (G11): Stop hook warns when a session changed a repo with no kb-spec log
H="$(cd "$(dirname "$0")/.." && pwd)/hooks/kb-log-guard.sh"
T=$(cd "$(mktemp -d)" && pwd -P); fails=0
export KB_LOG_GUARD_CACHE="$T/cache"
TODAY=$(date +%Y-%m-%d)

mkrepo() { mkdir -p "$T/$1" && git -C "$T/$1" init -q && echo x > "$T/$1/a.txt"; }
edit_line() { printf '{"type":"assistant","message":{"role":"assistant","content":[{"type":"tool_use","name":"%s","input":{"%s":"%s"}}]}}\n' "$1" "${3:-file_path}" "$2"; }

run() { # name transcript_content session -> sets out rc
  printf '%s' "$2" > "$T/$1.jsonl"
  out=$(printf '{"transcript_path":"%s","session_id":"%s","cwd":"%s"}' "$T/$1.jsonl" "${3:-$1}" "$T" | "$H" 2>/dev/null); rc=$?
}
want_warn() { if [ "$rc" = 0 ] && printf '%s' "$out" | grep -q 'kb-log-guard (G11)' && printf '%s' "$out" | grep -q "$2"; then echo "ok   $1"; else echo "FAIL $1 (rc=$rc) out=$out"; fails=1; fi; }
want_quiet() { if [ "$rc" = 0 ] && [ -z "$out" ]; then echo "ok   $1"; else echo "FAIL $1 (rc=$rc) out=$out"; fails=1; fi; }

mkrepo r1; mkrepo r2; mkrepo r3; mkrepo r4; mkrepo r5
mkdir -p "$T/r2/specs/_session"; : > "$T/r2/specs/_session/$TODAY-tasks.md"
mkdir -p "$T/scratch/claude-501/x"; echo y > "$T/scratch/claude-501/x/f.txt"

run edit-no-log "$(edit_line Edit "$T/r1/a.txt")"; want_warn edit-no-log "$T/r1"
run notebook-no-log "$(edit_line NotebookEdit "$T/r5/a.txt" notebook_path)" nb; want_warn notebook-no-log "$T/r5"
run edit-with-log-file "$(edit_line Write "$T/r2/a.txt")"; want_quiet edit-with-log-file
run edit-with-skill "$(edit_line Edit "$T/r3/a.txt")
$(printf '{"type":"assistant","message":{"role":"assistant","content":[{"type":"tool_use","name":"Skill","input":{"skill":"kb-spec","args":"log \\"task\\""}}]}}')"; want_quiet edit-with-skill
run edit-with-slash "$(edit_line Edit "$T/r3/a.txt")
$(printf '{"type":"user","message":{"role":"user","content":"/kb-spec log \\"task\\""}}')" slash; want_quiet edit-with-slash
run scratch-only "$(edit_line Write "$T/scratch/claude-501/x/f.txt")"; want_quiet scratch-only
run non-git "$(edit_line Write "/nonexistent-dir/f.txt")"; want_quiet non-git
run commit-no-log "$(printf '{"type":"assistant","cwd":"%s","message":{"role":"assistant","content":[{"type":"tool_use","name":"Bash","input":{"command":"git commit -m x"}}]}}' "$T/r4")" commit; want_warn commit-no-log "$T/r4"
run commit-no-log "$(printf '{"type":"assistant","cwd":"%s","message":{"role":"assistant","content":[{"type":"tool_use","name":"Bash","input":{"command":"git commit -m x"}}]}}' "$T/r4")" commit; want_quiet second-run-once

# whole file is scanned: edit on line 1, 20000 filler lines after
{ edit_line Edit "$T/r1/a.txt"; i=0; while [ $i -lt 200 ]; do printf '{"type":"user","message":{"role":"user","content":"%0200d"}}\n' $i; i=$((i+1)); done; } > "$T/big.jsonl"
out=$(printf '{"transcript_path":"%s","session_id":"big"}' "$T/big.jsonl" | "$H" 2>/dev/null); rc=$?; want_warn edit-at-head-of-big "$T/r1"

out=$(printf 'not json at all' | "$H" 2>/dev/null); rc=$?; want_quiet malformed-json
out=$(printf '{"transcript_path":"/nonexistent/x.jsonl","session_id":"m"}' | "$H" 2>/dev/null); rc=$?; want_quiet missing-transcript

rm -rf "$T"; exit $fails
