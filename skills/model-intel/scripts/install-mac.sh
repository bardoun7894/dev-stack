#!/usr/bin/env bash
# Install the weekly launchd agent (Monday 07:30 local, StartCalendarInterval so a missed run fires after wake)
# and symlink the skill into ~/.claude/skills like dev-stack's install.sh does.
set -eu
HERE="$(cd "$(dirname "$0")" && pwd)"
SKILL="$(dirname "$HERE")"
LABEL=dev.mbardouni.model-intel
DEST="$HOME/Library/LaunchAgents/$LABEL.plist"
mkdir -p "$HOME/Library/LaunchAgents" "$HOME/Library/Logs" "$HOME/.claude/skills"
LINK="$HOME/.claude/skills/model-intel"
if [ ! -e "$LINK" ] && [ ! -L "$LINK" ]; then ln -s "$SKILL" "$LINK"; echo "linked $LINK"; fi
sed -e "s|__SCRIPT__|$HERE/weekly.sh|g" -e "s|__HOME__|$HOME|g" "$SKILL/launchd/$LABEL.plist" > "$DEST"
plutil -lint "$DEST" >/dev/null
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$DEST"
echo "installed $DEST"
