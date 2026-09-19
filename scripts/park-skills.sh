#!/usr/bin/env bash
# park-skills.sh — keep only the skills you use loaded in Claude Code sessions; park the rest where
# jev-skill-suggest still finds them (it ranks ~/.claude/skills-parked and points the agent at SKILL.md).
# Moves entries (usually symlinks) between ~/.claude/skills and ~/.claude/skills-parked. Nothing is deleted.
#
#   bash scripts/park-skills.sh keep <name>...     park every skill NOT listed
#   bash scripts/park-skills.sh park <name>...     park the listed skills
#   bash scripts/park-skills.sh unpark <name>...   bring skills back (unpark --all for everything)
#   add --dry-run anywhere to only print the moves
set -u
LIVE="$HOME/.claude/skills"
PARKED="$HOME/.claude/skills-parked"
DRY=0
args=()
for a in "$@"; do [ "$a" = "--dry-run" ] && DRY=1 || args+=("$a"); done
set -- "${args[@]:-}"
cmd="${1:-}"; shift || true
mkdir -p "$PARKED"

move() {  # move <name> <from> <to>
  local n="$1" from="$2/$1" to="$3/$1"
  [ -e "$from" ] || [ -L "$from" ] || { echo "  missing $from"; return; }
  if [ -e "$to" ] || [ -L "$to" ]; then echo "  exists  $to (left alone)"; return; fi
  if [ $DRY -eq 1 ]; then echo "  would move $n -> $3"; else mv "$from" "$to" && echo "  moved $n -> $3"; fi
}

case "$cmd" in
  keep)
    [ $# -gt 0 ] || { echo "keep needs at least one skill name"; exit 64; }
    for d in "$LIVE"/*; do
      n="$(basename "$d")"
      case " $* " in *" $n "*) ;; *) move "$n" "$LIVE" "$PARKED" ;; esac
    done ;;
  park)   for n in "$@"; do move "$n" "$LIVE" "$PARKED"; done ;;
  unpark)
    if [ "${1:-}" = "--all" ]; then set -- $(ls "$PARKED"); fi
    for n in "$@"; do move "$n" "$PARKED" "$LIVE"; done ;;
  *) sed -n '2,12p' "$0"; exit 64 ;;
esac
echo "loaded: $(ls "$LIVE" | wc -l | tr -d ' ')   parked: $(ls "$PARKED" | wc -l | tr -d ' ')"
