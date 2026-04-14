#!/usr/bin/env bash
# dev-stack installer
# Symlinks all skills (first-party + vendor) into ~/.claude/skills/,
# installs the user-prompt KB hook, and appends the standing rule to ~/.claude/CLAUDE.md.
# Idempotent — safe to re-run.
#
# Flags:
#   (no flags)          — install missing symlinks, leave existing alone
#   --update-symlinks   — also replace stale symlinks (existing symlinks that
#                          point somewhere OTHER than dev-stack will be removed
#                          and re-linked). Real files are still preserved.

set -euo pipefail

update_symlinks=0
case "${1:-}" in
  --update-symlinks) update_symlinks=1 ;;
  --help|-h)
    sed -n '3,12p' "$0" | sed 's/^# *//'
    exit 0
    ;;
esac

REPO="$(cd "$(dirname "$0")" && pwd)"
CLAUDE_HOME="${CLAUDE_HOME:-$HOME/.claude}"
SKILLS_DIR="$CLAUDE_HOME/skills"
HOOKS_DIR="$CLAUDE_HOME/hooks"
AGENTS_DIR="$CLAUDE_HOME/agents"

echo "==> dev-stack installer"
echo "    repo:             $REPO"
echo "    claude home:      $CLAUDE_HOME"
echo "    update-symlinks:  $([ $update_symlinks -eq 1 ] && echo yes || echo no)"
echo

mkdir -p "$SKILLS_DIR" "$HOOKS_DIR" "$AGENTS_DIR"

link_skill() {
  local src="$1"
  local name
  name="$(basename "$src")"
  local dst="$SKILLS_DIR/$name"

  if [ -L "$dst" ]; then
    # It's a symlink — check where it points
    local current_target
    current_target="$(readlink "$dst")"
    if [ "$current_target" = "$src" ]; then
      echo "  ok       $name (already linked to dev-stack)"
      return 0
    fi
    # Stale symlink (points elsewhere)
    if [ $update_symlinks -eq 1 ]; then
      rm "$dst"
      ln -s "$src" "$dst"
      echo "  updated  $name (was → $current_target)"
      return 0
    fi
    echo "  stale    $name → $current_target (run with --update-symlinks to fix)"
    return 0
  fi

  if [ -e "$dst" ]; then
    # It's a real file — never touch it
    echo "  skip     $name (real file exists, not a symlink — leaving alone)"
    return 0
  fi

  ln -s "$src" "$dst"
  echo "  link     $name"
}

# 1. First-party skills
echo "[1/5] first-party skills"
for s in "$REPO"/skills/*/; do
  link_skill "${s%/}"
done

# 2. Vendor: kb-skill (8 KB skills)
echo "[2/5] vendor: kb-skill"
if [ -d "$REPO/vendor/kb-skill/skills" ]; then
  for s in "$REPO"/vendor/kb-skill/skills/*/; do
    link_skill "${s%/}"
  done
else
  echo "  warning: vendor/kb-skill not found — run 'git submodule update --init' first"
fi

# 3. Vendor: superpowers (14 obra skills)
echo "[3/5] vendor: superpowers"
if [ -d "$REPO/vendor/superpowers/skills" ]; then
  for s in "$REPO"/vendor/superpowers/skills/*/; do
    link_skill "${s%/}"
  done
else
  echo "  warning: vendor/superpowers not found — run 'git submodule update --init' first"
fi

# 4. Vendor: local (bundled third-party skills with no upstream git source)
echo "[4/5] vendor: local"
if [ -d "$REPO/vendor/local/skills" ]; then
  for s in "$REPO"/vendor/local/skills/*/; do
    link_skill "${s%/}"
  done
fi

# 5. Hook
echo "[5/7] hook"
hook_src="$REPO/hooks/user-prompt-kb-check.sh"
hook_dst="$HOOKS_DIR/user-prompt-kb-check.sh"
if [ -L "$hook_dst" ]; then
  current_target="$(readlink "$hook_dst")"
  if [ "$current_target" = "$hook_src" ]; then
    echo "  ok       user-prompt-kb-check.sh (already linked to dev-stack)"
  elif [ $update_symlinks -eq 1 ]; then
    rm "$hook_dst"
    ln -s "$hook_src" "$hook_dst"
    echo "  updated  user-prompt-kb-check.sh (was → $current_target)"
  else
    echo "  stale    user-prompt-kb-check.sh → $current_target (run with --update-symlinks to fix)"
  fi
elif [ -e "$hook_dst" ]; then
  echo "  skip     user-prompt-kb-check.sh (real file exists, leaving alone)"
else
  ln -s "$hook_src" "$hook_dst"
  echo "  link     user-prompt-kb-check.sh"
fi

# 6. Agents (orchestrator + role specialists)
echo "[6/7] agents"
link_agent() {
  local src="$1"
  local name
  name="$(basename "$src")"
  local dst="$AGENTS_DIR/$name"

  if [ -L "$dst" ]; then
    local current_target
    current_target="$(readlink "$dst")"
    if [ "$current_target" = "$src" ]; then
      echo "  ok       $name (already linked to dev-stack)"
      return 0
    fi
    if [ $update_symlinks -eq 1 ]; then
      rm "$dst"
      ln -s "$src" "$dst"
      echo "  updated  $name (was → $current_target)"
      return 0
    fi
    echo "  stale    $name → $current_target (run with --update-symlinks to fix)"
    return 0
  fi

  if [ -e "$dst" ]; then
    echo "  skip     $name (real file exists, not a symlink — leaving alone)"
    return 0
  fi

  ln -s "$src" "$dst"
  echo "  link     $name"
}

if [ -d "$REPO/agents" ]; then
  for f in "$REPO"/agents/*.md; do
    [ -f "$f" ] || continue
    # Skip README-style files — only register actual agent definitions
    name="$(basename "$f")"
    case "$name" in
      README*|readme*) continue ;;
    esac
    link_agent "$f"
  done
fi

# 7. Bin (universal helpers like kb-capture)
echo "[7/7] bin"
LOCAL_BIN="${LOCAL_BIN:-$HOME/.local/bin}"
mkdir -p "$LOCAL_BIN"
if [ -d "$REPO/bin" ]; then
  for src in "$REPO"/bin/*; do
    [ -f "$src" ] || continue
    name="$(basename "$src")"
    dst="$LOCAL_BIN/$name"
    if [ -L "$dst" ]; then
      current_target="$(readlink "$dst")"
      if [ "$current_target" = "$src" ]; then
        echo "  ok       $name (already linked to dev-stack)"
      elif [ $update_symlinks -eq 1 ]; then
        rm "$dst"
        ln -s "$src" "$dst"
        chmod +x "$src"
        echo "  updated  $name (was → $current_target)"
      else
        echo "  stale    $name → $current_target (run with --update-symlinks to fix)"
      fi
    elif [ -e "$dst" ]; then
      if [ $update_symlinks -eq 1 ]; then
        # For bin, existing real files are likely stale hand-written copies.
        # Move aside as .bak and link to dev-stack.
        mv "$dst" "$dst.bak-$(date +%s)"
        ln -s "$src" "$dst"
        chmod +x "$src"
        echo "  updated  $name (real file backed up as $dst.bak-*, now linked to dev-stack)"
      else
        echo "  stale    $name (real file, not a symlink — run with --update-symlinks to replace it with a dev-stack symlink, original will be backed up)"
      fi
    else
      ln -s "$src" "$dst"
      chmod +x "$src"
      echo "  link     $name → $dst"
    fi
  done
  case ":$PATH:" in
    *":$LOCAL_BIN:"*) ;;
    *) echo "  warning: $LOCAL_BIN is not in your PATH — add 'export PATH=\"\$HOME/.local/bin:\$PATH\"' to your shell rc" ;;
  esac
fi

# Settings reminder
settings="$CLAUDE_HOME/settings.json"
if ! grep -q "user-prompt-kb-check.sh" "$settings" 2>/dev/null; then
  echo
  echo "==> NEXT STEP"
  echo "Add this to $settings under .hooks.UserPromptSubmit:"
  echo
  cat <<'JSON'
{
  "matcher": "",
  "hooks": [
    {
      "type": "command",
      "command": "bash $HOME/.claude/hooks/user-prompt-kb-check.sh",
      "timeout": 5
    }
  ]
}
JSON
fi

# CLAUDE.md snippet
clauder="$CLAUDE_HOME/CLAUDE.md"
if [ -f "$clauder" ] && ! grep -q "kb-dev" "$clauder" 2>/dev/null; then
  echo
  echo "==> Append the standing rule from $REPO/CLAUDE.md.snippet to $clauder"
  echo "    (review first; we do not append automatically)"
fi

echo
echo "==> done."
