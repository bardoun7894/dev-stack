#!/usr/bin/env bash
# Test for skills/market-swot/scripts/x-summarize.sh with a stubbed pi
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
SCRIPT="$HERE/../../skills/market-swot/scripts/x-summarize.sh"
fail=0
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
mkdir "$T/bin"
echo 'POST https://x.com/a/status/1 UNIQUE_MARKER_42' > "$T/posts.md"
stub() { cat > "$T/bin/pi" <<E
#!/usr/bin/env bash
printf '%s\n' "\$@" > "$T/args.txt"
$1
E
chmod +x "$T/bin/pi"; }

bash "$SCRIPT" >/dev/null 2>&1; [ $? -eq 2 ] || { echo "FAIL no-arg exit want=2"; fail=1; }

stub 'echo "theme one https://x.com/a/status/1"'
out="$(PATH="$T/bin:$PATH" bash "$SCRIPT" "$T/posts.md")"; rc=$?
[ "$rc" -eq 0 ] || { echo "FAIL success rc=$rc"; fail=1; }
echo "$out" | grep -q 'theme one' || { echo "FAIL summary not printed"; fail=1; }
grep -q 'UNIQUE_MARKER_42' "$T/args.txt" || { echo "FAIL posts content not in prompt"; fail=1; }
grep -q 'commandcode/xai/grok-4.7' "$T/args.txt" || { echo "FAIL model flag"; fail=1; }

stub 'exit 0'
out="$(PATH="$T/bin:$PATH" bash "$SCRIPT" "$T/posts.md" 2>&1)"; rc=$?
[ "$rc" -eq 3 ] || { echo "FAIL empty output rc want=3 got=$rc"; fail=1; }
echo "$out" | grep -q 'grok unavailable' || { echo "FAIL message"; fail=1; }

stub 'echo "429" >&2; exit 1'
PATH="$T/bin:$PATH" bash "$SCRIPT" "$T/posts.md" >/dev/null 2>&1; [ $? -eq 3 ] || { echo "FAIL nonzero rc want=3"; fail=1; }

[ "$fail" -eq 0 ] && echo "PASS all market-swot x_summarize_test.sh assertions"
exit $fail
