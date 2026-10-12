#!/usr/bin/env bash
# Mirror the skill to MyContabo with rsync (no git on the server) and install the Monday 06:00 cron line.
# The server run proposes only (MODEL_INTEL_NO_APPLY=1): the Mac owns tiers.json changes.
# Usage: install-server.sh [--dry-run]
set -eu
HERE="$(cd "$(dirname "$0")" && pwd)"
SKILL="$(dirname "$HERE")"
HOST="${MODEL_INTEL_SSH_HOST:-MyContabo}"
DEST=/root/.claude/skills/model-intel
RS=(-az --delete --exclude data/ --exclude __pycache__/ --exclude tests/)
[ "${1:-}" = "--dry-run" ] && RS+=(-n -v)
ssh -o BatchMode=yes "$HOST" "mkdir -p $DEST"
rsync "${RS[@]}" "$SKILL/" "$HOST:$DEST/"
[ "${1:-}" = "--dry-run" ] && exit 0
CRON='0 6 * * 1 PATH=/root/.local/bin:/usr/local/bin:/usr/bin:/bin MODEL_INTEL_NO_APPLY=1 MODEL_INTEL_NO_NOTIFY=1 flock -n /run/model-intel.lock bash /root/.claude/skills/model-intel/scripts/weekly.sh >> /var/log/model-intel.log 2>&1 # model-intel'
ssh -o BatchMode=yes "$HOST" "(crontab -l 2>/dev/null | grep -v '# model-intel\$'; echo '$CRON') | crontab -"
ssh -o BatchMode=yes "$HOST" "crontab -l | grep model-intel"
