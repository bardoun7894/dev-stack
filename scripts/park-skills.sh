#!/usr/bin/env bash
# park-skills.sh — keep only the skills you use loaded in Claude Code sessions; park the rest where
# jev-skill-suggest still finds them (it ranks ~/.claude/skills-parked and points the agent at SKILL.md).
# Moves entries (usually symlinks) between ~/.claude/skills and ~/.claude/skills-parked. Nothing is deleted.
#
#   bash scripts/park-skills.sh keep <name>...     park every skill NOT listed
#   bash scripts/park-skills.sh park <name>...     park the listed skills
#   bash scripts/park-skills.sh unpark <name>...   bring skills back (unpark --all for everything)
#   bash scripts/park-skills.sh dedupe             drop ~/.claude/skills symlinks whose name is also parked
#                                                  (only when the parked copy resolves to a SKILL.md and both
#                                                  links resolve to the same real path; otherwise reported, kept)
#   bash scripts/park-skills.sh park-agent <name>...    move ~/.claude/agents/<name>.md to agents-parked
#   bash scripts/park-skills.sh unpark-agent <name>...  back again (unpark-agent --all for everything)
#   bash scripts/park-skills.sh keep-agents <name>...   park every agent NOT listed
#   bash scripts/park-skills.sh auto [--apply] [--force]  park/unpark by real use (capabilities.json + policy
#                                                  config/capability-policy.json); dry-run unless --apply.
#                                                  Refuses without usage data (usage.jsonl empty, scan read 0
#                                                  files) and refuses --apply when it would park more than 8
#                                                  items, unless --force
#   add --dry-run anywhere to only print the moves
set -u
HERE="$(cd "$(dirname "$(readlink -f "$0" 2>/dev/null || echo "$0")")" && pwd)"
LIVE="$HOME/.claude/skills"
PARKED="$HOME/.claude/skills-parked"
DRY=0
APPLY=0
FORCE=0
MAX_PARKS=8
args=()
# each name is its own argument; a single quoted "a b c" is split too
for a in "$@"; do
  case "$a" in
    --dry-run) DRY=1 ;;
    --apply) APPLY=1 ;;
    --force) FORCE=1 ;;
    *) for w in $a; do args+=("$w"); done ;;
  esac
done
set -- ${args[@]+"${args[@]}"}
cmd="${1:-}"; shift || true
ALIVE="$HOME/.claude/agents"
APARKED="$HOME/.claude/agents-parked"
mkdir -p "$PARKED"

move() {  # move <name> <from> <to>
  local n="$1" from="$2/$1" to="$3/$1"
  [ -e "$from" ] || [ -L "$from" ] || { echo "  missing $from"; return; }
  if [ -e "$to" ] || [ -L "$to" ]; then echo "  exists  $to (left alone)"; return; fi
  if [ $DRY -eq 1 ]; then echo "  would move $n -> $3"; else mv "$from" "$to" && echo "  moved $n -> $3"; fi
}

dedupe() {
  local d n t
  for d in "$LIVE"/*; do
    [ -L "$d" ] || continue
    n="$(basename "$d")"
    [ -f "$PARKED/$n/SKILL.md" ] || continue
    t="$(readlink "$d")"
    # Only a parked copy that is the very same real path makes the live link redundant; an older or different
    # target (e.g. the live link points into the dev-stack repo) may be the newer one, so report and keep it.
    if [ "$(realpath "$d" 2>/dev/null)" != "$(realpath "$PARKED/$n" 2>/dev/null)" ]; then
      echo "  kept    $n (live -> $t differs from the parked copy; not removed)"
      continue
    fi
    if [ $DRY -eq 1 ]; then echo "  would remove $n (symlink -> $t)"
    else rm "$d" && echo "  removed $n (symlink -> $t)"; fi
  done
}

auto() {
  local policy="${CAPABILITY_POLICY:-$HERE/../config/capability-policy.json}" plan line verb kind n rest
  [ $APPLY -eq 1 ] || DRY=1
  plan="$(python3 "$HERE/capability-registry.py" park-plan "$policy" 2>&1)" || { echo "auto: no usable registry/policy/usage data (run bin/capability-refresh first): $plan"; exit 1; }
  [ -n "$plan" ] || { echo "  nothing to move"; return; }
  parks=$(printf '%s\n' "$plan" | grep -c '^park ')
  if [ $APPLY -eq 1 ] && [ $FORCE -eq 0 ] && [ "$parks" -gt $MAX_PARKS ]; then
    echo "auto: the plan parks $parks items (more than $MAX_PARKS); read it without --apply, then pass --force to apply it"
    exit 1
  fi
  while read -r verb kind n rest; do
    [ -n "$verb" ] || continue
    case "$verb:$kind" in
      real:*) echo "  skipped $n ($rest)" ;;
      park:skill) move "$n" "$LIVE" "$PARKED" ;;
      unpark:skill) move "$n" "$PARKED" "$LIVE" ;;
      park:agent) mkdir -p "$APARKED"; move "$n.md" "$ALIVE" "$APARKED" ;;
      unpark:agent) move "$n.md" "$APARKED" "$ALIVE" ;;
    esac
  done <<< "$plan"
  [ $DRY -eq 1 ] && echo "dry run: pass --apply to move"
}

case "$cmd" in
  auto) auto ;;
  dedupe) dedupe ;;
  park-agent)   [ $# -gt 0 ] || { echo "park-agent needs a name"; exit 64; }
                mkdir -p "$APARKED"; for n in "$@"; do move "$n.md" "$ALIVE" "$APARKED"; done ;;
  unpark-agent)
    mkdir -p "$APARKED"
    if [ "${1:-}" = "--all" ]; then set -- $(ls "$APARKED"); else set -- "${@/%/.md}"; fi
    for n in "$@"; do move "$n" "$APARKED" "$ALIVE"; done ;;
  keep-agents)
    [ $# -gt 0 ] || { echo "keep-agents needs at least one agent name"; exit 64; }
    mkdir -p "$APARKED"
    for d in "$ALIVE"/*.md; do
      [ -e "$d" ] || [ -L "$d" ] || continue
      n="$(basename "$d" .md)"
      case " $* " in *" $n "*) ;; *) move "$n.md" "$ALIVE" "$APARKED" ;; esac
    done ;;
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
  *) sed -n '2,18p' "$0"; exit 64 ;;
esac
case "$cmd" in *-agent*|keep-agents) echo "agents loaded: $(ls "$ALIVE" | wc -l | tr -d ' ')   parked: $(ls "$APARKED" | wc -l | tr -d ' ')"; exit 0 ;; esac
echo "loaded: $(ls "$LIVE" | wc -l | tr -d ' ')   parked: $(ls "$PARKED" | wc -l | tr -d ' ')"
