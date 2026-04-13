#!/usr/bin/env bash
# dev-stack installer
# Symlinks all skills (first-party + vendor) into ~/.claude/skills/,
# installs the user-prompt KB hook, and appends the standing rule to ~/.claude/CLAUDE.md.
# Idempotent — safe to re-run.

set -euo pipefail

REPO="$(cd "$(dirname "$0")" && pwd)"
CLAUDE_HOME="${CLAUDE_HOME:-$HOME/.claude}"
SKILLS_DIR="$CLAUDE_HOME/skills"
HOOKS_DIR="$CLAUDE_HOME/hooks"

echo "==> dev-stack installer"
echo "    repo:        $REPO"
echo "    claude home: $CLAUDE_HOME"
echo

mkdir -p "$SKILLS_DIR" "$HOOKS_DIR"

link_skill() {
  local src="$1"
  local name
  name="$(basename "$src")"
  local dst="$SKILLS_DIR/$name"
  if [ -L "$dst" ] || [ -e "$dst" ]; then
    if [ -L "$dst" ] && [ "$(readlink "$dst")" = "$src" ]; then
      echo "  ok   $name (already linked)"
      return 0
    fi
    echo "  skip $name (exists, not ours — leaving alone)"
    return 0
  fi
  ln -s "$src" "$dst"
  echo "  link $name"
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
echo "[5/6] hook"
hook_src="$REPO/hooks/user-prompt-kb-check.sh"
hook_dst="$HOOKS_DIR/user-prompt-kb-check.sh"
if [ -L "$hook_dst" ] && [ "$(readlink "$hook_dst")" = "$hook_src" ]; then
  echo "  ok   user-prompt-kb-check.sh (already linked)"
elif [ -e "$hook_dst" ]; then
  echo "  skip user-prompt-kb-check.sh (exists, not ours — leaving alone)"
else
  ln -s "$hook_src" "$hook_dst"
  echo "  link user-prompt-kb-check.sh"
fi

# 6. Bin (universal helpers like kb-capture)
echo "[6/6] bin"
LOCAL_BIN="${LOCAL_BIN:-$HOME/.local/bin}"
mkdir -p "$LOCAL_BIN"
if [ -d "$REPO/bin" ]; then
  for src in "$REPO"/bin/*; do
    [ -f "$src" ] || continue
    name="$(basename "$src")"
    dst="$LOCAL_BIN/$name"
    if [ -L "$dst" ] && [ "$(readlink "$dst")" = "$src" ]; then
      echo "  ok   $name (already linked)"
    elif [ -e "$dst" ]; then
      echo "  skip $name (exists, not ours — leaving alone)"
    else
      ln -s "$src" "$dst"
      chmod +x "$src"
      echo "  link $name → $dst"
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
