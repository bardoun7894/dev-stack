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

# tar -h sends what a symlink points at (skills are links into dev-stack), so every link must resolve inside an
# allowed root: a link to ~/.ssh or a credentials file stops the run before anything is sent. Depth 5 stops loops.
ROOTS=(${MIRROR_LINK_ROOTS:-"$SRC" "$HOME/.agents" "$HOME/code" "$HOME/Developer" "$HOME/projects"})
inside() { local p=$1 r; for r in "${ROOTS[@]}"; do r=$(readlink -f "$r" 2>/dev/null) || continue; case $p in "$r"|"$r"/*) return 0 ;; esac; done; return 1; }
check_links() {
  local dir=$1 depth=$2 l t
  [ "$depth" -le 5 ] || { echo "mirror: symlinks nest deeper than 5 under $dir (loop?), nothing sent" >&2; return 1; }
  while IFS= read -r l; do
    t=$(readlink -f "$l" 2>/dev/null) && [ -e "$t" ] || { echo "mirror: broken symlink $l, nothing sent" >&2; return 1; }
    inside "$t" || { echo "mirror: $l points outside the allowed roots ($t), nothing sent" >&2; return 1; }
    if [ -d "$t" ]; then check_links "$t" $((depth + 1)) || return 1; fi
  done < <(find "$dir" \( -name .venv -o -name node_modules -o -name .git -o -name '*.bak*' -o -name __pycache__ \) -prune \
             -o -type l -print 2>/dev/null)
}
for i in "${ITEMS[@]}"; do if [ -e "$SRC/$i" ]; then check_links "$SRC/$i" 0 || exit 1; fi; done

for h in "${HOSTS[@]}"; do
  if [ "$dry" = 1 ]; then
    echo "would mirror ${ITEMS[*]} from $SRC to $h:/root/.claude"
    continue
  fi
  echo "mirror -> $h"
  COPYFILE_DISABLE=1 tar --no-xattrs -C "$SRC" -h -cf - --exclude='*.bak*' --exclude='__pycache__' --exclude='.venv' --exclude='node_modules' --exclude='.git' \
    --exclude='.env' --exclude='.env.*' --exclude='*.pem' --exclude='*.key' --exclude='id_rsa*' --exclude='id_ed25519*' "${ITEMS[@]}" \
    | ssh -o BatchMode=yes -o ConnectTimeout=15 "$h" 'mkdir -p ~/.claude && tar --overwrite -C ~/.claude -xf -'
done
