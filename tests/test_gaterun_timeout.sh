#!/bin/bash
# gaterun.sh: a gate past GATE_TIMEOUT is killed (exit 124, log line); a quick gate keeps its own exit code;
# testcap.sh: the count-file name pattern is valid for tr on GNU and BSD.
set -u
SRC=$(cd "$(dirname "$0")/../scripts/gate" && pwd)
T=$(mktemp -d); trap 'kill $PID 2>/dev/null; rm -rf "$T"' EXIT
fail=0; check() { if eval "$2"; then echo "ok   $1"; else echo "FAIL $1"; fail=1; fi; }

if ! command -v timeout >/dev/null && ! command -v gtimeout >/dev/null; then echo "skip: no timeout(1)"; exit 0; fi
mkdir -p "$T/gate" "$T/repo/.worktrees/slow" "$T/repo/.worktrees/fast" "$T/home"
cp "$SRC/gaterun.sh" "$T/gate/"
cat > "$T/gate/gate.sh" <<'EOF'
#!/bin/bash
case $2 in slow) sleep 30 ;; fast) exit 7 ;; esac
EOF
echo "MAX_PARALLEL=2" > "$T/repo/.gate.conf"
S=$T/home/.cache/gate/repo; mkdir -p "$S"
printf 'slow slow\nfast fast\n' > "$S/gateq.txt"
HOME=$T/home GATE_TIMEOUT=2s POLL=1 bash "$T/gate/gaterun.sh" "$T/repo" & PID=$!
for _ in $(seq 1 90); do [ -f "$S/gate-slow.done" ] && [ -f "$S/gate-fast.done" ] && break; sleep 1; done
check "slow gate killed with 124" '[ "$(cat "$S/gate-slow.done" 2>/dev/null)" = 124 ]'
check "slow gate log says timeout" 'grep -q "GATE TIMEOUT slow after 2s" "$S/gate-slow.log"'
check "fast gate keeps its exit code" '[ "$(cat "$S/gate-fast.done" 2>/dev/null)" = 7 ]'
check "fast gate log has no timeout line" '! grep -q "GATE TIMEOUT" "$S/gate-fast.log"'

check "testcap name pattern accepted by tr" 'printf "/a b/c@feat/x" | tr -c "A-Za-z0-9._\n-" "_" >/dev/null 2>&1'
check "testcap name pattern keeps dash and dot" '[ "$(printf "a-b.c d" | tr -c "A-Za-z0-9._\n-" "_")" = "a-b.c_d" ]'
exit $fail
