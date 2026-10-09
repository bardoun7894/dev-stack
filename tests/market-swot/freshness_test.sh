#!/usr/bin/env bash
# Test for skills/market-swot/scripts/freshness.sh
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
SCRIPT="$HERE/../../skills/market-swot/scripts/freshness.sh"
fail=0
command -v jq >/dev/null || { echo "FAIL jq not installed"; exit 1; }
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
ago() { date -v-"$1"d +%F 2>/dev/null || date -d "$1 days ago" +%F; }
printf 'last_refreshed: %s\n# x\n' "$(ago 2)"  > "$T/fresh.md"
printf 'last_refreshed: %s\n# x\n' "$(ago 20)" > "$T/stale.md"
printf '# no stamp\n' > "$T/missing.md"

out="$(bash "$SCRIPT" "$T/fresh.md" "$T/stale.md" "$T/missing.md")"; rc=$?
[ "$rc" -eq 0 ] || { echo "FAIL exit=$rc"; fail=1; }
echo "$out" | jq . >/dev/null 2>&1 || { echo "FAIL not JSON"; echo "$out"; exit 1; }
g() { echo "$out" | jq -r --arg f "$1" ".[] | select(.file==\$f) | .$2"; }
[ "$(g "$T/fresh.md" stale)" = "false" ] || { echo "FAIL fresh stale want=false"; fail=1; }
[ "$(g "$T/fresh.md" age_days)" = "2" ] || { echo "FAIL fresh age want=2 got=$(g "$T/fresh.md" age_days)"; fail=1; }
[ "$(g "$T/stale.md" stale)" = "true" ] || { echo "FAIL stale stale want=true"; fail=1; }
[ "$(g "$T/missing.md" stale)" = "true" ] || { echo "FAIL missing stale want=true"; fail=1; }
[ "$(g "$T/missing.md" last_refreshed)" = "null" ] || { echo "FAIL missing stamp want=null"; fail=1; }
out2="$(FRESH_MAX_DAYS=30 bash "$SCRIPT" "$T/stale.md")"
[ "$(echo "$out2" | jq -r '.[0].stale')" = "false" ] || { echo "FAIL override want stale=false"; fail=1; }

[ "$fail" -eq 0 ] && echo "PASS all market-swot freshness_test.sh assertions"
exit $fail
