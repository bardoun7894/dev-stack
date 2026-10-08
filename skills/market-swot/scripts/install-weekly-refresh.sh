#!/usr/bin/env bash
# skills/market-swot/scripts/install-weekly-refresh.sh [--dry-run|--uninstall]
# Installs a launchd agent: every Monday 09:00 local runs `claude -p "/market-swot refresh"`.
set -u
LABEL="dev.mbardouni.market-swot-refresh"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG="$HOME/.cache/market-swot/refresh.log"
CLAUDE="$(command -v claude || echo claude)"
plist() {
cat <<E
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>-c</string>
    <string>$CLAUDE -p "/market-swot refresh" --allowedTools "Bash Read Edit Write WebSearch WebFetch" &lt;/dev/null</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Weekday</key>
    <integer>1</integer>
    <key>Hour</key>
    <integer>9</integer>
    <key>Minute</key>
    <integer>0</integer>
  </dict>
  <key>StandardOutPath</key>
  <string>$LOG</string>
  <key>StandardErrorPath</key>
  <string>$LOG</string>
</dict>
</plist>
E
}
case "${1:-}" in
  --dry-run) plist ;;
  --uninstall)
    launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
    rm -f "$PLIST"; echo "uninstalled $LABEL" ;;
  "")
    mkdir -p "$(dirname "$PLIST")" "$(dirname "$LOG")"
    plist > "$PLIST"
    launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
    launchctl bootstrap "gui/$(id -u)" "$PLIST" && echo "installed $LABEL (Mondays 09:00)" ;;
  *) echo "usage: $0 [--dry-run|--uninstall]" >&2; exit 2 ;;
esac
