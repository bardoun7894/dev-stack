#!/bin/bash
# Capability regression suite: runs scripts/evals/tasks/*.sh (exit 0 pass, 1 fail, 2 skip;
# one evidence line on stdout), writes a JSON result + latest.md, sends a one-line Telegram summary.
# Usage: brain-evals.sh [--if-changed] [--only NAME] [--no-notify]
set -u
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
DIR="$(cd "$(dirname "$0")" && pwd)"
TASKS_DIR="${BRAIN_EVALS_TASKS_DIR:-$DIR/tasks}"
STATE_DIR="${BRAIN_EVALS_STATE_DIR:-$HOME/.local/state/brain-evals}"
TASK_TIMEOUT="${BRAIN_EVALS_TIMEOUT:-600}"
FP_FILE="$STATE_DIR/fingerprint"
MAX_AGE=$((7 * 86400))

# Cron has none of the shell's env (same as router-health.sh).
[ -f "$HOME/.config/tokyo/cliproxy.env" ] && { set -a; . "$HOME/.config/tokyo/cliproxy.env"; set +a; }

IF_CHANGED=0 ONLY="" NOTIFY=1
while [ $# -gt 0 ]; do
  case "$1" in
    --if-changed) IF_CHANGED=1 ;;
    --only) ONLY="${2:-}"; shift ;;
    --no-notify) NOTIFY=0 ;;
    *) echo "usage: brain-evals.sh [--if-changed] [--only NAME] [--no-notify]" >&2; exit 2 ;;
  esac
  shift
done
mkdir -p "$STATE_DIR"

fingerprint() {
  if [ -n "${BRAIN_EVALS_FINGERPRINT_CMD:-}" ]; then
    sh -c "$BRAIN_EVALS_FINGERPRINT_CMD" 2>&1
  else
    { cat "$HOME/.config/jev-router/tiers.json" 2>/dev/null
      claude --version 2>&1
      jdelegate --help 2>&1 | head -3; }
  fi | shasum -a 256 | cut -d' ' -f1
}
FP="$(fingerprint)"

if [ "$IF_CHANGED" = 1 ] && [ -f "$FP_FILE" ]; then
  age=$(( $(date +%s) - $(stat -f %m "$FP_FILE" 2>/dev/null || stat -c %Y "$FP_FILE") ))
  if [ "$(cat "$FP_FILE")" = "$FP" ] && [ "$age" -lt "$MAX_AGE" ]; then
    echo unchanged
    exit 0
  fi
fi

# timeout(1) is absent on stock macOS; fall back to perl alarm.
run_with_timeout() {
  local secs="$1"; shift
  if command -v timeout >/dev/null; then timeout "$secs" "$@"
  elif command -v gtimeout >/dev/null; then gtimeout "$secs" "$@"
  else perl -e 'alarm shift; exec @ARGV or exit 127' "$secs" "$@"; fi
}

stamp="$(date +%Y-%m-%d-%H%M)"
RESULT="$STATE_DIR/$stamp.json"
[ -e "$RESULT" ] && RESULT="$STATE_DIR/$stamp-$(date +%S)-$$.json"
rows="$(mktemp)"; out="$(mktemp)"; trap 'rm -f "$rows" "$out"' EXIT
pass=0 total=0 failed=()

for t in "$TASKS_DIR"/*.sh; do
  [ -f "$t" ] || continue
  name="$(basename "$t" .sh)"
  [ -n "$ONLY" ] && [ "$ONLY" != "$name" ] && continue
  start=$(date +%s)
  run_with_timeout "$TASK_TIMEOUT" bash "$t" >"$out" 2>&1 </dev/null
  rc=$?
  ev="$(tail -1 "$out")"
  secs=$(( $(date +%s) - start ))
  case "$rc" in
    0) status=pass; pass=$((pass+1)); total=$((total+1)) ;;
    2) status=skip ;;
    124|142) status=fail; ev="timeout after ${TASK_TIMEOUT}s: $ev"; total=$((total+1)); failed+=("$name") ;;
    *) status=fail; total=$((total+1)); failed+=("$name") ;;
  esac
  jq -nc --arg n "$name" --arg s "$status" --argjson t "$secs" --arg e "$ev" \
    '{task:$n,status:$s,seconds:$t,evidence:$e}' >> "$rows"
done

jq -s --arg ts "$(date -u +%FT%TZ)" --arg fp "$FP" '{time:$ts,fingerprint:$fp,tasks:.}' "$rows" > "$RESULT"
{
  echo "# brain-evals $(date '+%Y-%m-%d %H:%M')"
  echo
  echo "| task | status | seconds | evidence |"
  echo "|------|--------|---------|----------|"
  jq -r '.tasks[] | "| \(.task) | \(.status) | \(.seconds) | \(.evidence | gsub("\\|";"/")) |"' "$RESULT"
} > "$STATE_DIR/latest.md"
printf '%s' "$FP" > "$FP_FILE"

summary="[brain-evals] $pass/$total pass"
[ "${#failed[@]}" -gt 0 ] && summary="$summary: failed ${failed[*]}"
echo "$summary"

if [ "$NOTIFY" = 1 ]; then
  # Same payload and curl as send_telegram() in scripts/server/server-health.sh, run on the server
  # so the token never leaves it.
  printf '%s' "$summary" | ssh -o ConnectTimeout=8 MyContabo 'MSG=$(cat); . /root/tokyo/.env 2>/dev/null
    [ -n "${TELEGRAM_BOT_TOKEN:-}" ] && [ -n "${TELEGRAM_USER_ID:-}" ] || exit 1
    CID="$TELEGRAM_USER_ID" MSG="$MSG" python3 -c "import json,os;print(json.dumps({\"chat_id\":os.environ[\"CID\"],\"text\":os.environ[\"MSG\"]}))" |
    curl -sS -f -m 20 -H "Content-Type: application/json" -X POST --data-binary @- "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" >/dev/null 2>&1' \
    >/dev/null 2>&1 || echo "notify skipped" >&2
fi

[ "${#failed[@]}" -gt 0 ] && exit 1
exit 0
