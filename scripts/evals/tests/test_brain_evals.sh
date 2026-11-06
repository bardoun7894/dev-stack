#!/bin/bash
# Tests for brain-evals.sh using fake task scripts. Run: bash scripts/evals/tests/test_brain_evals.sh
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
RUN="$HERE/../brain-evals.sh"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
fails=0
ok() { echo "ok   $1"; }
bad() { echo "FAIL $1"; fails=$((fails+1)); }
check() { if [ "$2" = "$3" ]; then ok "$1"; else bad "$1 (got '$2', want '$3')"; fi; }

export BRAIN_EVALS_TASKS_DIR="$T/tasks" BRAIN_EVALS_STATE_DIR="$T/state" BRAIN_EVALS_FINGERPRINT_CMD="cat $T/fp"
mkdir -p "$T/tasks"; echo v1 > "$T/fp"
mk() { printf '#!/bin/bash\necho "%s evidence"\nexit %s\n' "$1" "$2" > "$T/tasks/$1.sh"; }
mk a-pass 0; mk b-fail 1; mk c-skip 2

out=$(bash "$RUN" --no-notify 2>&1); rc=$?
check "exit 1 when a task fails" "$rc" 1
latest="$T/state/latest.md"
[ -f "$latest" ] && ok "latest.md written" || bad "latest.md missing"
check "one json result" "$(ls "$T"/state/*.json | grep -v fingerprint | wc -l | tr -d ' ')" 1
j=$(ls "$T"/state/2*.json)
check "pass count" "$(jq '[.tasks[]|select(.status=="pass")]|length' "$j")" 1
check "fail count" "$(jq '[.tasks[]|select(.status=="fail")]|length' "$j")" 1
check "skip count" "$(jq '[.tasks[]|select(.status=="skip")]|length' "$j")" 1
grep -q "a-pass evidence" "$latest" && ok "evidence in latest.md" || bad "evidence missing"
echo "$out" | grep -q "1/2 pass: failed b-fail" && ok "summary line" || bad "summary line: $out"

# --only
rm -rf "$T/state"; rm "$T/tasks/b-fail.sh"
bash "$RUN" --no-notify --only a-pass >/dev/null 2>&1; rc=$?
check "only: exit 0" "$rc" 0
check "only: one task" "$(jq '.tasks|length' "$T"/state/2*.json)" 1

# --if-changed
rm -rf "$T/state"
bash "$RUN" --no-notify --if-changed >/dev/null 2>&1
check "if-changed first run executes" "$(ls "$T"/state/2*.json 2>/dev/null | wc -l | tr -d ' ')" 1
out=$(bash "$RUN" --no-notify --if-changed 2>&1)
check "if-changed unchanged prints unchanged" "$(echo "$out" | tail -1)" unchanged
echo v2 > "$T/fp"
bash "$RUN" --no-notify --if-changed >/dev/null 2>&1
check "if-changed changed re-runs" "$(ls "$T"/state/2*.json | wc -l | tr -d ' ')" 2

[ "$fails" = 0 ] && echo "ALL PASS" || { echo "$fails FAILED"; exit 1; }
