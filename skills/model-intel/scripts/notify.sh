#!/usr/bin/env bash
# Send stdin as a Telegram message, reusing the tokyo server's /root/tokyo/.env (same token as server-health).
# On the server it sends directly; from the Mac it runs the same sender over ssh MyContabo. Never fails the caller.
set -u
ENV_FILE="${MODEL_INTEL_ENV_FILE:-/root/tokyo/.env}"
HOST="${MODEL_INTEL_SSH_HOST-MyContabo}"
MSG="$(cat)"
[ -n "$MSG" ] || exit 0
B64="$(printf '%s' "$MSG" | base64 | tr -d '\n')"
read -r -d '' SENDER <<'EOS'
set -a; . "$ENV_FILE" 2>/dev/null; set +a
[ -n "${TELEGRAM_BOT_TOKEN:-}" ] && [ -n "${TELEGRAM_USER_ID:-}" ] || exit 1
printf '%s' "$B64" | base64 -d | python3 -c 'import json,os,sys;print(json.dumps({"chat_id":os.environ["TELEGRAM_USER_ID"],"text":sys.stdin.read()[:3900]}))' \
  | curl -sS -f -m 20 -H "Content-Type: application/json" -X POST --data-binary @- "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" >/dev/null
EOS
if [ -r "$ENV_FILE" ]; then
  ENV_FILE="$ENV_FILE" B64="$B64" bash -c "$SENDER" 2>/dev/null
elif [ -n "$HOST" ]; then
  ssh -o BatchMode=yes -o ConnectTimeout=8 "$HOST" "ENV_FILE=$ENV_FILE B64=$B64 bash -s" <<< "$SENDER" 2>/dev/null
fi
exit 0
