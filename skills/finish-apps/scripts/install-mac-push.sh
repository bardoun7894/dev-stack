#!/usr/bin/env bash
# Install the launchd agent that pushes the Mac project snapshot every 2 hours.
set -eu
HERE="$(cd "$(dirname "$0")" && pwd)"
LABEL=dev.mbardouni.finish-apps-push
DEST="$HOME/Library/LaunchAgents/$LABEL.plist"
mkdir -p "$HOME/Library/LaunchAgents" "$HOME/Library/Logs"
sed -e "s|__SCRIPT__|$HERE/push-mac-snapshot.sh|g" -e "s|__HOME__|$HOME|g" \
  "$HERE/../launchd/$LABEL.plist" > "$DEST"
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$DEST"
echo "installed $DEST"
