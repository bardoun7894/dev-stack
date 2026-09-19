#!/usr/bin/env bash
# sync-jev-harnesses.sh — make the jev skill and the Jev-first rule visible to every agent harness on this
# machine, not only Claude Code. Idempotent: links are only created when missing, and the rule block is
# replaced between its BEGIN/END markers. Every edited instruction file gets a one-time .bak-jev copy.
#
#   bash scripts/sync-jev-harnesses.sh            # apply
#   bash scripts/sync-jev-harnesses.sh --dry-run  # show what would change
set -u
DRY=0; [ "${1:-}" = "--dry-run" ] && DRY=1
REPO="$(cd "$(dirname "$(readlink -f "$0" 2>/dev/null || echo "$0")")/.." && pwd)"
SKILL="$REPO/skills/jev"
RULE="$REPO/skills/jev/references/jev-first-rule.md"
[ -d "$SKILL" ] && [ -f "$RULE" ] || { echo "missing $SKILL or $RULE"; exit 1; }

run() { if [ $DRY -eq 1 ]; then echo "  would: $*"; else "$@"; fi; }

echo "== skill links"
# Shared agent-skills dir first (Codex, OpenCode, Kimi Code read it); curated harnesses link through it.
link() {  # link <skills dir> <target>
  local dir="$1" target="$2"
  [ -d "$dir" ] || { echo "  skip  $dir (harness not installed)"; return; }
  if [ -e "$dir/jev" ] || [ -L "$dir/jev" ]; then echo "  ok    $dir/jev"; return; fi
  run ln -s "$target" "$dir/jev" && [ $DRY -eq 0 ] && echo "  link  $dir/jev -> $target"
}
link "$HOME/.agents/skills"            "$SKILL"
link "$HOME/.claude/skills"            "$SKILL"
link "$HOME/.pi/agent/skills"          "$SKILL"
link "$HOME/.config/opencode/skills"   "$SKILL"
link "$HOME/.hermes/skills"            "$HOME/.agents/skills/jev"
link "$HOME/.continue/skills"          "$HOME/.agents/skills/jev"
link "$HOME/.gemini/skills"            "$HOME/.agents/skills/jev"
link "$HOME/.gemini/config/skills"     "$HOME/.agents/skills/jev"   # Antigravity (agy)

echo "== Jev-first rule in global instructions"
put_rule() {  # put_rule <file> [create]
  local f="$1" create="${2:-}"
  if [ ! -f "$f" ]; then
    [ -n "$create" ] && [ -d "$(dirname "$f")" ] || { echo "  skip  $f"; return; }
    run cp "$RULE" "$f" && [ $DRY -eq 0 ] && echo "  new   $f"
    return
  fi
  if grep -q "BEGIN jev-first" "$f"; then
    if [ $DRY -eq 1 ]; then echo "  would refresh $f"; return; fi
    python3 "$REPO/scripts/_replace_block.py" "$f" "$RULE" && echo "  sync  $f"
  else
    if [ $DRY -eq 1 ]; then echo "  would append to $f"; return; fi
    [ -e "$f.bak-jev" ] || cp "$f" "$f.bak-jev"
    printf '\n' >> "$f" && cat "$RULE" >> "$f" && echo "  add   $f"
  fi
}
put_rule "$HOME/.codex/AGENTS.md" create
put_rule "$HOME/.config/opencode/AGENTS.md" create
put_rule "$HOME/.pi/agent/AGENTS.md"
put_rule "$HOME/.gemini/GEMINI.md"
put_rule "$HOME/.hermes/HERMES.md" create
put_rule "$HOME/.continue/rules/jev-first.md" create
