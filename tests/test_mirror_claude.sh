#!/bin/bash
# bash tests/test_mirror_claude.sh — scripts/mirror-claude-to-servers.sh: both servers are targets, only the rule paths go
S="$(cd "$(dirname "$0")/.." && pwd)/scripts/mirror-claude-to-servers.sh"
fails=0
check() { # name cond-exit-code
  if [ "$2" = 0 ]; then echo "ok   $1"; else echo "FAIL $1"; fails=1; fi
}

out=$("$S" --dry-run 2>&1); rc=$?
check "dry-run exits 0" $rc
printf '%s' "$out" | grep -q 'MyContabo';    check "MyContabo is a target" $?
printf '%s' "$out" | grep -q 'MediaContabo'; check "MediaContabo is a target" $?
for p in CLAUDE.md comms.md reference agents-parked skills skills-parked; do
  printf '%s' "$out" | grep -q "$p"; check "mirrors $p" $?
done
printf '%s' "$out" | grep -q 'settings.json'; [ $? -ne 0 ]; check "never mirrors settings.json" $?
out=$("$S" --dry-run MediaContabo 2>&1)
printf '%s' "$out" | grep -q 'MyContabo'; [ $? -ne 0 ]; check "explicit host limits targets" $?
[ $fails = 0 ] && echo "ALL OK" || exit 1
