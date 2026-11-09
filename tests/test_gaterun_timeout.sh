#!/bin/bash
# gaterun.sh time limit: a gate past GATE_TIMEOUT is killed and logged (TERM -> 124, TERM ignored -> KILL -> 137);
# a gate that exits 124 itself is not called a timeout; env GATE_TIMEOUT beats .gate.conf; no timeout(1) -> no limit.
# testcap.sh: the count file of a branch with '/' and '-' is named with the GNU-safe pattern.
set -u
SRC=$(cd "$(dirname "$0")/../scripts/gate" && pwd)
PID=; T=$(mktemp -d)
cleanup() { [ -n "$PID" ] && kill "$PID" 2>/dev/null; pkill -f "$T/" 2>/dev/null; rm -rf "$T"; }
trap cleanup EXIT
fail=0; check() { if eval "$2"; then echo "ok   $1"; else echo "FAIL $1"; fail=1; fi; }
TO_BIN=$(command -v timeout || command -v gtimeout || true)
[ -n "$TO_BIN" ] || { echo "FAIL timeout(1)/gtimeout not installed: the time-limit path cannot be tested"; exit 1; }

mkdir -p "$T/gate" "$T/home"
cp "$SRC/gaterun.sh" "$T/gate/"
cat > "$T/gate/gate.sh" <<'EOF'
#!/bin/bash
case $2 in
  slow) sleep 30 ;;
  hard) trap '' TERM; for _ in $(seq 1 30); do sleep 1; done ;;
  own124) exit 124 ;;
  fast) exit 7 ;;
esac
EOF
# start_queue <repo> <jobs...>: run gaterun on a fresh repo dir until every job has a .done file (max 90 s)
start_queue() {
  local repo=$1; shift; mkdir -p "$T/$repo"; local S=$T/home/.cache/gate/$repo; mkdir -p "$S"
  : > "$S/gateq.txt"; for j in "$@"; do echo "$j $T/$repo" >> "$S/gateq.txt"; done
  HOME=$T/home POLL=1 bash "$T/gate/gaterun.sh" "$T/$repo" & PID=$!
  for _ in $(seq 1 90); do local all=1; for j in "$@"; do [ -f "$S/gate-$j.done" ] || all=0; done; [ $all = 1 ] && break; sleep 1; done
  kill "$PID" 2>/dev/null; wait "$PID" 2>/dev/null; PID=
}

# A: limit from env beats a long .gate.conf limit; TERM path, KILL path, own 124, plain exit code.
mkdir -p "$T/a"; printf 'MAX_PARALLEL=4\nGATE_TIMEOUT=1h\n' > "$T/a/.gate.conf"
GATE_TIMEOUT=2s GATE_KILL_AFTER=1 start_queue a slow hard own124 fast
A=$T/home/.cache/gate/a
check "env GATE_TIMEOUT beats .gate.conf: slow gate killed with 124" '[ "$(cat "$A/gate-slow.done" 2>/dev/null)" = 124 ]'
check "slow gate log says timeout" 'grep -q "GATE TIMEOUT slow after 2s" "$A/gate-slow.log"'
check "TERM-ignoring gate is killed (137) and logged" '[ "$(cat "$A/gate-hard.done" 2>/dev/null)" = 137 ] && grep -q "GATE TIMEOUT hard" "$A/gate-hard.log"'
check "a gate exiting 124 itself is not a timeout" '[ "$(cat "$A/gate-own124.done" 2>/dev/null)" = 124 ] && ! grep -q "GATE TIMEOUT" "$A/gate-own124.log"'
check "fast gate keeps its exit code" '[ "$(cat "$A/gate-fast.done" 2>/dev/null)" = 7 ] && ! grep -q "GATE TIMEOUT" "$A/gate-fast.log"'

# B: a bad limit falls back to 45m and says so.
mkdir -p "$T/b"; echo "MAX_PARALLEL=1" > "$T/b/.gate.conf"
GATE_TIMEOUT="45 m" start_queue b fast
check "bad GATE_TIMEOUT is logged and the gate still runs" 'grep -q "bad GATE_TIMEOUT" "$T/home/.cache/gate/b/gate-fast.log" && [ "$(cat "$T/home/.cache/gate/b/gate-fast.done")" = 7 ]'

# C: no timeout(1): the gate runs without a limit and the log says so.
mkdir -p "$T/c"; echo "MAX_PARALLEL=1" > "$T/c/.gate.conf"
GATERUN_TIMEOUT_BIN= start_queue c fast
check "no timeout(1): runs without a limit, logged" 'grep -q "runs without a time limit" "$T/home/.cache/gate/c/gate-fast.log" && [ "$(cat "$T/home/.cache/gate/c/gate-fast.done")" = 7 ]'

# D: the real testcap.sh on a branch with '/' and '-'.
R=$T/repo; git init -q "$R" && git -C "$R" -c user.email=t@t -c user.name=t commit -q --allow-empty -m init && git -C "$R" checkout -q -b feat/x-y
out=$(cd "$R" && HOME=$T/home bash "$SRC/testcap.sh" "$T/out.txt" -- true 2>&1); rc=$?
check "testcap runs on a branch with / and -" '[ $rc = 0 ]'
check "testcap count file keeps - and . and maps /" 'ls "$T/home/.cache/gate/testcap/" | grep -q "repo_feat_x-y.count$"'
exit $fail
