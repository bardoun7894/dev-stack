#!/usr/bin/env bash
# Test for skills/market-swot/scripts/install-weekly-refresh.sh (dry-run only, temp HOME)
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
SCRIPT="$HERE/../../skills/market-swot/scripts/install-weekly-refresh.sh"
fail=0
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
out="$(HOME="$T" bash "$SCRIPT" --dry-run)"; rc=$?
[ "$rc" -eq 0 ] || { echo "FAIL rc=$rc"; fail=1; }
for needle in "dev.mbardouni.market-swot-refresh" "Weekday" "/market-swot refresh" "refresh.log" "--allowedTools"; do
  echo "$out" | grep -q -- "$needle" || { echo "FAIL missing: $needle"; fail=1; }
done
echo "$out" | grep -A1 Weekday | grep -q '<integer>1</integer>' || { echo "FAIL Weekday 1"; fail=1; }
echo "$out" | grep -A1 Hour | grep -q '<integer>9</integer>' || { echo "FAIL Hour 9"; fail=1; }
for needle in EnvironmentVariables WorkingDirectory "/opt/homebrew/bin" "$T/.claude/skills/market-swot"; do
  echo "$out" | grep -q -- "$needle" || { echo "FAIL missing: $needle"; fail=1; }
done
echo "$out" | grep -A1 '<key>HOME</key>' | grep -q "<string>$T</string>" || { echo "FAIL HOME env"; fail=1; }
if command -v plutil >/dev/null; then echo "$out" | plutil -lint - >/dev/null 2>&1 || { echo "FAIL plutil lint"; fail=1; }; fi
[ ! -e "$T/Library/LaunchAgents/dev.mbardouni.market-swot-refresh.plist" ] || { echo "FAIL dry-run wrote plist"; fail=1; }
[ "$fail" -eq 0 ] && echo "PASS all market-swot install_refresh_test.sh assertions"
exit $fail
