#!/usr/bin/env bash
# mirror-claude-to-servers.sh — copy the owner's rules and skills from ~/.claude to every server.
#
#   scripts/mirror-claude-to-servers.sh [--dry-run] [host ...]
#
# Hosts default to MyContabo and MediaContabo (override with MIRROR_HOSTS="a b"). Only the paths the
# standing rules say are mirrored are sent; settings.json is never touched (each server has its own
# env, hooks and auth). Backup files (*.bak*) stay home. Tar over ssh: rsync is not on every box.
set -euo pipefail

SRC="${CLAUDE_HOME:-$HOME/.claude}"
ITEMS=(CLAUDE.md comms.md reference agents-parked skills skills-parked)
HOSTS=(${MIRROR_HOSTS:-MyContabo MediaContabo})
dry=0
args=()
for a in "$@"; do
  if [ "$a" = "--dry-run" ]; then dry=1; else args+=("$a"); fi
done
[ ${#args[@]} -gt 0 ] && HOSTS=("${args[@]}")

for h in "${HOSTS[@]}"; do
  if [ "$dry" = 1 ]; then
    echo "would mirror ${ITEMS[*]} from $SRC to $h:/root/.claude"
    continue
  fi
  echo "mirror -> $h"
  COPYFILE_DISABLE=1 tar --no-xattrs -C "$SRC" -h -cf - --exclude='*.bak*' --exclude='__pycache__' "${ITEMS[@]}" \
    | ssh -o BatchMode=yes -o ConnectTimeout=15 "$h" 'mkdir -p ~/.claude && tar --overwrite -C ~/.claude -xf -'
done
