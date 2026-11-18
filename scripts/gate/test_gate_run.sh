#!/usr/bin/env bash
# Tests for gate-run FIFO ticket queue and the -merge timeout cap. Run: bash test_gate_run.sh [path/to/gate-run]
set -u
GR=${1:-$(cd "$(dirname "$0")" && pwd)/gate-run}
T=$(mktemp -d /tmp/gate-run-test.XXXXXX); trap 'rm -rf "$T"' EXIT
export GATE_DIR=$T/gate FACTORY_CONTROL_DIR=$T/ctl FACTORY_FRUN=/bin/true GATE_SLOTS=0 GATE_SHARED_TMP=1
fail=0
ok() { echo "ok   $1"; }
bad() { echo "FAIL $1"; fail=1; }

# 1. three waiters arrive in order A, B, C while a holder runs; they must acquire in that order
out=$T/order; : > "$out"
bash "$GR" fifo 1m -- sleep 4 >/dev/null 2>&1 &
sleep 0.7
for n in A B C; do
  bash "$GR" fifo 1m -- bash -c "echo $n >> $out; sleep 0.3" >/dev/null 2>&1 &
  sleep 0.5
done
wait
[ "$(tr '\n' ' ' < "$out")" = "A B C " ] && ok "waiters acquire in arrival order" || bad "order was: $(tr '\n' ' ' < "$out")"
[ -z "$(ls "$GATE_DIR/queue/fifo" 2>/dev/null)" ] && ok "queue empty after run" || bad "tickets left: $(ls "$GATE_DIR/queue/fifo")"

# 2. a ticket of a dead pid, older than ours, is skipped and removed
mkdir -p "$GATE_DIR/queue/dead"
true & dp=$!; wait $dp
echo $dp > "$GATE_DIR/queue/dead/1000000000000000000-$dp"
bash "$GR" dead 1m -- bash -c "echo ran > $T/dead.out" >/dev/null 2>&1; rc=$?
[ "$rc" = 0 ] && [ "$(cat "$T/dead.out" 2>/dev/null)" = ran ] && ok "dead ticket skipped (rc 0)" || bad "dead ticket blocked the queue (rc $rc)"
[ -z "$(ls "$GATE_DIR/queue/dead")" ] && ok "dead ticket removed" || bad "dead ticket still there"

# 3. -merge lock refuses a timeout above 90m, accepts 90m
bash "$GR" proj-merge 3h -- true >"$T/m.out" 2>&1; rc=$?
[ "$rc" = 2 ] && grep -q "merges only" "$T/m.out" && ok "-merge 3h refused (exit 2)" || bad "-merge 3h gave rc $rc"
bash "$GR" proj-merge 90m -- true >/dev/null 2>&1; rc=$?
[ "$rc" = 0 ] && ok "-merge 90m accepted" || bad "-merge 90m gave rc $rc"
bash "$GR" proj-other 3h -- true >/dev/null 2>&1; rc=$?
[ "$rc" = 0 ] && ok "non-merge 3h accepted" || bad "non-merge 3h gave rc $rc"

# 4. lock wait timeout still exits 75
bash "$GR" wt 1m -- sleep 4 >/dev/null 2>&1 & sleep 0.5
GATE_WAIT=1 bash "$GR" wt 1m -- true >/dev/null 2>&1; rc=$?; wait
[ "$rc" = 75 ] && ok "wait timeout exits 75" || bad "wait timeout rc $rc"

[ $fail = 0 ] && echo "PASS: all gate-run tests" || { echo "FAILED"; exit 1; }
