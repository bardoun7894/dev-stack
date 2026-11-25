#!/usr/bin/env bash
# link-harnesses.sh — make xDesignSkill usable by every agent harness on this machine, not
# only Claude Code, and put the `xdesign` command on the PATH. Idempotent: a link is only
# created when missing, and a link that points somewhere else is reported, never replaced.
#
#   bash link-harnesses.sh            # apply
#   bash link-harnesses.sh --dry-run  # show what would change
set -u
DRY=0; [ "${1:-}" = "--dry-run" ] && DRY=1
SELF="$(readlink -f "$0" 2>/dev/null || python3 -c 'import os,sys;print(os.path.realpath(sys.argv[1]))' "$0")"
SKILL="$(cd "$(dirname "$SELF")/.." && pwd)"
NAME="$(basename "$SKILL")"
[ -f "$SKILL/SKILL.md" ] || { echo "no SKILL.md in $SKILL"; exit 1; }

link() {  # link <link path> <target>
  local at="$1" target="$2"
  if [ -L "$at" ] && [ "$(readlink "$at")" = "$target" ]; then echo "  ok    $at"; return; fi
  if [ -e "$at" ] || [ -L "$at" ]; then echo "  KEPT  $at (exists, points elsewhere: $(readlink "$at" 2>/dev/null || echo 'not a link'))"; return; fi
  if [ $DRY -eq 1 ]; then echo "  would link $at -> $target"; else ln -s "$target" "$at" && echo "  link  $at -> $target"; fi
}

echo "== skill links ($NAME)"
# ~/.agents/skills is the shared folder (Codex, OpenCode, Kimi Code read it); the rest are per harness.
# Gemini CLI reads ~/.agents/skills itself; a second link in ~/.gemini/skills only adds a conflict warning.
for dir in "$HOME/.agents/skills" "$HOME/.claude/skills" "$HOME/.codex/skills" \
           "$HOME/.gemini/config/skills" "$HOME/.pi/skills" "$HOME/.pi/agent/skills" "$HOME/.config/opencode/skills" \
           "$HOME/.cursor/skills" "$HOME/.hermes/skills" "$HOME/.continue/skills"; do
  if [ -d "$dir" ]; then link "$dir/$NAME" "$SKILL"; else echo "  skip  $dir (harness not installed)"; fi
done

echo "== command"
chmod +x "$SKILL/scripts/xdesign.mjs" 2>/dev/null
mkdir -p "$HOME/.local/bin"
link "$HOME/.local/bin/xdesign" "$SKILL/scripts/xdesign.mjs"
case ":$PATH:" in *":$HOME/.local/bin:"*) ;; *) echo "  note  $HOME/.local/bin is not on PATH in this shell";; esac
