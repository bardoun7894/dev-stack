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

  # Parked skills stay parked: re-linking them would load their description into every session again.
  if [ -e "$CLAUDE_HOME/skills-parked/$name" ] || [ -L "$CLAUDE_HOME/skills-parked/$name" ]; then
    echo "  parked   $name"
    return 0
  fi

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

TOTAL_PHASES=10

# 1. First-party skills
echo "[1/$TOTAL_PHASES] first-party skills"
for s in "$REPO"/skills/*/; do
  link_skill "${s%/}"
done

# 2. Vendor: kb-skill (8 KB skills)
echo "[2/$TOTAL_PHASES] vendor: kb-skill"
if [ -d "$REPO/vendor/kb-skill/skills" ]; then
  for s in "$REPO"/vendor/kb-skill/skills/*/; do
    link_skill "${s%/}"
  done
else
  echo "  warning: vendor/kb-skill not found — run 'git submodule update --init' first"
fi

# 3. Vendor: superpowers (14 obra skills)
echo "[3/$TOTAL_PHASES] vendor: superpowers"
if [ -d "$REPO/vendor/superpowers/skills" ]; then
  for s in "$REPO"/vendor/superpowers/skills/*/; do
    link_skill "${s%/}"
  done
else
  echo "  warning: vendor/superpowers not found — run 'git submodule update --init' first"
fi

# 4. Vendor: local (bundled third-party skills with no upstream git source)
echo "[4/$TOTAL_PHASES] vendor: local"
if [ -d "$REPO/vendor/local/skills" ]; then
  for s in "$REPO"/vendor/local/skills/*/; do
    link_skill "${s%/}"
  done
fi

# 5. Hooks
echo "[5/$TOTAL_PHASES] hooks"
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

# 5b. view-md auto-fire Stop hook
viewmd_hook_src="$REPO/hooks/view-md-stop.sh"
viewmd_hook_dst="$HOOKS_DIR/view-md-stop.sh"
if [ -f "$viewmd_hook_src" ]; then
  if [ -L "$viewmd_hook_dst" ]; then
    current_target="$(readlink "$viewmd_hook_dst")"
    if [ "$current_target" = "$viewmd_hook_src" ]; then
      echo "  ok       view-md-stop.sh (already linked to dev-stack)"
    elif [ $update_symlinks -eq 1 ]; then
      rm "$viewmd_hook_dst"
      ln -s "$viewmd_hook_src" "$viewmd_hook_dst"
      chmod +x "$viewmd_hook_src"
      echo "  updated  view-md-stop.sh (was → $current_target)"
    else
      echo "  stale    view-md-stop.sh → $current_target (run with --update-symlinks to fix)"
    fi
  elif [ -e "$viewmd_hook_dst" ]; then
    echo "  skip     view-md-stop.sh (real file exists, leaving alone)"
  else
    ln -s "$viewmd_hook_src" "$viewmd_hook_dst"
    chmod +x "$viewmd_hook_src"
    echo "  link     view-md-stop.sh"
  fi
fi

# 5c. install-guard PreToolUse supply-chain hook
ig_hook_src="$REPO/hooks/install-guard.sh"
ig_hook_dst="$HOOKS_DIR/install-guard.sh"
if [ -f "$ig_hook_src" ]; then
  if [ -L "$ig_hook_dst" ]; then
    current_target="$(readlink "$ig_hook_dst")"
    if [ "$current_target" = "$ig_hook_src" ]; then
      echo "  ok       install-guard.sh (already linked to dev-stack)"
    elif [ $update_symlinks -eq 1 ]; then
      rm "$ig_hook_dst"
      ln -s "$ig_hook_src" "$ig_hook_dst"
      chmod +x "$ig_hook_src"
      echo "  updated  install-guard.sh (was → $current_target)"
    else
      echo "  stale    install-guard.sh → $current_target (run with --update-symlinks to fix)"
    fi
  elif [ -e "$ig_hook_dst" ]; then
    echo "  skip     install-guard.sh (real file exists, leaving alone)"
  else
    ln -s "$ig_hook_src" "$ig_hook_dst"
    chmod +x "$ig_hook_src"
    echo "  link     install-guard.sh"
  fi
fi

# 6. Agents (orchestrator + role specialists)
echo "[6/$TOTAL_PHASES] agents"
link_agent() {
  local src="$1"
  local name
  name="$(basename "$src")"
  local dst="$AGENTS_DIR/$name"

  if [ -e "$CLAUDE_HOME/agents-parked/$name" ] || [ -L "$CLAUDE_HOME/agents-parked/$name" ]; then
    echo "  parked   $name"
    return 0
  fi

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
echo "[7/$TOTAL_PHASES] bin"
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

# 8. OpenCode agent skills (full pipeline — symlinked to `~/.agents/skills/`)
echo "[8/$TOTAL_PHASES] opencode agent skills"
OC_AGENTS_DIR="${OC_AGENTS_DIR:-$HOME/.agents/skills}"
mkdir -p "$OC_AGENTS_DIR"

link_agentskill() {
  local src="$1"
  local name
  name="$(basename "$src")"
  local dst="$OC_AGENTS_DIR/$name"

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
    # Real file — back up if --update-symlinks
    if [ $update_symlinks -eq 1 ]; then
      mv "$dst" "$dst.bak-$(date +%s)"
      ln -s "$src" "$dst"
      echo "  updated  $name (real file backed up, now linked)"
      return 0
    fi
    echo "  skip     $name (real file exists — run with --update-symlinks to replace with symlink)"
    return 0
  fi

  ln -s "$src" "$dst"
  echo "  link     $name"
}

# All first-party + vendor skills
OC_SKILL_SOURCES=()
for tier in "$REPO/skills" "$REPO/vendor/kb-skill/skills" "$REPO/vendor/superpowers/skills" "$REPO/vendor/local/skills"; do
  [ -d "$tier" ] && for s in "$tier"/*/; do
    [ -d "$s" ] && OC_SKILL_SOURCES+=("${s%/}")
  done
done

for src in "${OC_SKILL_SOURCES[@]}"; do
  link_agentskill "$src"
done

# 8b. External skills (from ~/.claude/skills/ — no dev-stack source)
echo "  -- external skills --"
EXTERNAL_SKILLS=("check-project-inbox" "dogfood" "github" "opencode" "surian-deploy" "voice-coach")
for name in "${EXTERNAL_SKILLS[@]}"; do
  src="$CLAUDE_HOME/skills/$name"
  dst="$OC_AGENTS_DIR/$name"
  if [ -d "$src" ]; then
    if [ -L "$dst" ]; then
      echo "  ok       $name (already linked)"
    elif [ -e "$dst" ]; then
      if [ $update_symlinks -eq 1 ]; then
        mv "$dst" "$dst.bak-$(date +%s)"
        ln -s "$src" "$dst"
        echo "  linked   $name (real file backed up)"
      else
        echo "  skip     $name (real file exists)"
      fi
    else
      ln -s "$src" "$dst"
      echo "  linked   $name"
    fi
  elif [ -d "$CLAUDE_HOME/skills-parked/$name" ]; then
    echo "  parked   $name (not linked into OpenCode)"
  else
    echo "  skip     $name (source missing at $src)"
  fi
done

# 9. OpenCode plugin & slash commands
echo "[9/$TOTAL_PHASES] opencode plugin & commands"
OPENCODE_SLASH_SKILLS=(
  "audit" "brainstorming" "kb-query" "kb-spec"
  "polish" "systematic-debugging" "test-driven-development"
  "verification-before-completion" "view-md" "writing-plans"
)
OC_CMDS_DIR="$HOME/.config/opencode/superpowers/commands"
if [ -d "$HOME/.config/opencode" ]; then
  mkdir -p "$OC_CMDS_DIR"
  for skill_name in "${OPENCODE_SLASH_SKILLS[@]}"; do
    # Search across all tiers for the SKILL.md
    src=""
    for tier in "$REPO/skills" "$REPO/vendor/kb-skill/skills" "$REPO/vendor/superpowers/skills" "$REPO/vendor/local/skills"; do
      candidate="$tier/$skill_name/SKILL.md"
      [ -f "$candidate" ] && { src="$candidate"; break; }
    done
    [ -z "$src" ] && { echo "  warning: slash source missing for $skill_name"; continue; }

    # Slash-command wrapper (idempotent)
    cmd_dst="$OC_CMDS_DIR/$skill_name.md"
    if [ ! -e "$cmd_dst" ] || grep -q "Invoke the superpowers:$skill_name skill" "$cmd_dst" 2>/dev/null; then
      cat > "$cmd_dst" <<EOF
---
description: "Invoke the $skill_name skill (auto-installed by dev-stack)."
disable-model-invocation: true
---

Invoke the superpowers:$skill_name skill and follow it exactly as presented to you.
EOF
      echo "  ok       /$skill_name slash command"
    else
      echo "  skip     /$skill_name slash command (custom user content, leaving alone)"
    fi
  done
else
  echo "  skip     opencode not installed (~/.config/opencode missing)"
fi

# 10. Settings reminder for Stop hook
echo "[10/$TOTAL_PHASES] settings hints"
settings_file="$CLAUDE_HOME/settings.json"
if ! grep -q "view-md-stop.sh" "$settings_file" 2>/dev/null; then
  echo "  add the following to $settings_file under .hooks.Stop[].hooks to auto-render Arabic + mermaid responses:"
  cat <<'JSON'
    {
      "type": "command",
      "command": "bash $HOME/.claude/hooks/view-md-stop.sh",
      "timeout": 5,
      "async": true
    }
JSON
else
  echo "  ok       view-md-stop.sh already wired in $settings_file"
fi

if ! grep -q "install-guard.sh" "$settings_file" 2>/dev/null; then
  ig_entry='{"matcher":"Bash|mcp__lean-ctx__ctx_shell","hooks":[{"type":"command","command":"$HOME/.claude/hooks/install-guard.sh","timeout":5}]}'
  if command -v jq >/dev/null 2>&1 && [ -f "$settings_file" ] \
     && jq --argjson e "$ig_entry" '.hooks.PreToolUse = ((.hooks.PreToolUse // []) + [$e])' "$settings_file" > "$settings_file.ig.tmp" 2>/dev/null; then
    cp "$settings_file" "$settings_file.bak-install-guard"
    mv "$settings_file.ig.tmp" "$settings_file"
    echo "  wired    install-guard.sh into $settings_file (backup: $settings_file.bak-install-guard)"
  else
    rm -f "$settings_file.ig.tmp"
    echo "  WARNING  install-guard.sh is NOT active. Add this to $settings_file under .hooks.PreToolUse[]:"
    echo "$ig_entry"
  fi
else
  echo "  ok       install-guard.sh already wired in $settings_file"
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
