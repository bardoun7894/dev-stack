#!/usr/bin/env bash
# Fixture test for skills/finish-apps/scripts/push-mac-snapshot.sh
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
SCRIPT="$HERE/../../skills/finish-apps/scripts/push-mac-snapshot.sh"
ACTIVE="$HERE/../../skills/finish-apps/scripts/active.sh"
fail=0
command -v jq >/dev/null || { echo "FAIL jq not installed"; exit 1; }
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
export GIT_AUTHOR_NAME=Test GIT_AUTHOR_EMAIL=t@e.com GIT_COMMITTER_NAME=Test GIT_COMMITTER_EMAIL=t@e.com
P="$T/projects"; mkdir -p "$P/one"; git -C "$P/one" init -q -b work
echo 1 > "$P/one/f"; git -C "$P/one" add -A; git -C "$P/one" commit -q -m c
B="$T/bin"; mkdir -p "$B"
cat > "$B/ssh" <<'S'
#!/usr/bin/env bash
echo "$*" >> "$STUB_LOG"
[ -z "${STUB_FAIL:-}" ] || exit 255
cat > "$STUB_UP"
S
chmod +x "$B/ssh"
export STUB_LOG="$T/ssh.log" STUB_UP="$T/uploaded.json" HOME="$T/home"; mkdir -p "$HOME"
push() { PATH="$B:$PATH" FINISH_APPS_MAC_ROOTS="${ROOTS:-$P/*}" bash "$SCRIPT"; }

: > "$STUB_LOG"; rm -f "$STUB_UP"
push; rc=$?
[ "$rc" -eq 0 ] || { echo "FAIL push exit=$rc"; fail=1; }
want="$(FINISH_APPS_SELF=mac FINISH_APPS_SSH_HOST= FINISH_APPS_MAC_ROOTS="$P/*" bash "$ACTIVE" --host mac --days 7 | jq -S .)"
[ "$(jq -S . "$STUB_UP" 2>/dev/null)" = "$want" ] && [ -n "$want" ] || { echo "FAIL uploaded JSON differs from active.sh output"; fail=1; }
grep -q 'ConnectTimeout=8' "$STUB_LOG" && grep -q 'BatchMode=yes' "$STUB_LOG" && grep -q 'MyContabo' "$STUB_LOG" \
  && grep -q 'mac-latest.json.tmp' "$STUB_LOG" && grep -q 'mv ' "$STUB_LOG" || { echo "FAIL ssh invocation: $(cat "$STUB_LOG")"; fail=1; }
[ -s "$HOME/Library/Logs/finish-apps-push.log" ] || { echo "FAIL no log line"; fail=1; }

: > "$STUB_LOG"; rm -f "$STUB_UP"
STUB_FAIL=1 push; rc=$?
[ "$rc" -ne 0 ] || { echo "FAIL ssh failure should exit non-zero"; fail=1; }

: > "$STUB_LOG"; rm -f "$STUB_UP"; mkdir -p "$T/empty"
ROOTS="$T/empty/*" push; rc=$?
[ "$rc" -ne 0 ] || { echo "FAIL empty scan should exit non-zero"; fail=1; }
[ ! -s "$STUB_LOG" ] && [ ! -e "$STUB_UP" ] || { echo "FAIL empty scan must not upload"; fail=1; }

[ "$fail" -eq 0 ] && echo "PASS push_test"
exit "$fail"
