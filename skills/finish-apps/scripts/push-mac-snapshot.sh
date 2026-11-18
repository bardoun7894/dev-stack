#!/usr/bin/env bash
# skills/finish-apps/scripts/push-mac-snapshot.sh
# Run on the Mac: scan active projects and upload the JSON to the server so the server sweep can
# include Mac-only projects without ssh-ing to the Mac. Upload is atomic (tmp + mv).
# Env: FINISH_APPS_PUSH_HOST (default MyContabo), FINISH_APPS_PUSH_PATH (default /root/.tokyo/finish-apps/mac-latest.json).
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
HOST="${FINISH_APPS_PUSH_HOST:-MyContabo}"
DEST="${FINISH_APPS_PUSH_PATH:-/root/.tokyo/finish-apps/mac-latest.json}"
LOG="$HOME/Library/Logs/finish-apps-push.log"
mkdir -p "$(dirname "$LOG")"
tmp="$(mktemp)"; trap 'rm -f "$tmp"' EXIT

log() { printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" | tee -a "$LOG" >&2; }

FINISH_APPS_SELF=mac FINISH_APPS_SSH_HOST= bash "$HERE/active.sh" --host mac --days 7 > "$tmp" 2>/dev/null \
  || { log "FAIL scan failed"; exit 1; }
n="$(jq -e 'if type=="array" and length>0 then length else empty end' "$tmp" 2>/dev/null)" \
  || { log "FAIL scan empty or invalid; nothing uploaded"; exit 1; }

q() { printf '%q' "$1"; }
ssh -o ConnectTimeout=8 -o BatchMode=yes "$HOST" \
  "mkdir -p $(q "$(dirname "$DEST")") && cat > $(q "$DEST.tmp") && mv $(q "$DEST.tmp") $(q "$DEST")" < "$tmp" \
  || { log "FAIL upload to $HOST:$DEST"; exit 1; }
log "OK pushed $n projects to $HOST:$DEST"
