#!/usr/bin/env bash
# Tests for gate-status: LOST tickets older than 6h are archived to tickets/lost/ and only counted.
#   bash scripts/gate/test_gate_status.sh
set -uo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
export GATE_DIR=$T/gate GATE_LEGACY_LOCK=$T/none.lock
mkdir -p "$GATE_DIR/tickets"
fail=0
ok() { if eval "$2"; then echo "ok   $1"; else echo "FAIL $1"; fail=1; fi; }
mk() { # id age_hours
  local b=$GATE_DIR/tickets/$1
  echo "2026-10-30T00:00:00Z x" > "$b.started"; echo 999999 > "$b.pid"; echo /tmp > "$b.cwd"; echo "true" > "$b.cmd"; : > "$b.out"
  touch -d "$2 hours ago" "$b.started"
}
mk old-lost 7; mk new-lost 1
out=$(bash "$HERE/gate-status" 2>&1)
ok "old LOST ticket is not listed" '! grep -q "^old-lost" <<<"$out"'
ok "recent LOST ticket is still listed" 'grep -q "^new-lost .*LOST" <<<"$out"'
ok "old LOST files moved to lost/" '[ -e "$GATE_DIR/tickets/lost/old-lost.started" ] && [ ! -e "$GATE_DIR/tickets/old-lost.started" ]'
ok "recent LOST ticket stays in place" '[ -e "$GATE_DIR/tickets/new-lost.started" ]'
ok "a count line is shown" 'grep -q "lost tickets archived.*: 1 in" <<<"$out"'
out2=$(bash "$HERE/gate-status" 2>&1)
ok "second run keeps the count and moves nothing" 'grep -q "archived.*: 1 in .*(0 moved now)" <<<"$out2"'
exit $fail
