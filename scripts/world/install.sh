#!/usr/bin/env bash
# install.sh — copy the launchd plist to ~/Library/LaunchAgents and link
# `track` + `world-push` into ~/.local/bin.  Re-run idempotently.
#
# Not auto-run by world-push; the user invokes this once after checkout.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
LABEL="dev.mbardouni.world-push"
LAUNCH_AGENTS="$HOME/Library/LaunchAgents"
LOCAL_BIN="${LOCAL_BIN:-$HOME/.local/bin}"

mkdir -p "$LAUNCH_AGENTS" "$LOCAL_BIN"

# Symlink the two scripts. If the source is a checkout (not on PATH),
# call python3 directly; if user prefers a wrapper, we honour that.
ln -sfn "$ROOT/track"      "$LOCAL_BIN/track"
ln -sfn "$ROOT/world-push" "$LOCAL_BIN/world-push"
chmod +x "$ROOT/track" "$ROOT/world-push"

# Ingest token: launchd gets only the path (WORLD_TOKEN_FILE in the plist); the file must be 0600.
TOKEN_FILE="$HOME/.config/world/token"
mkdir -p "$(dirname "$TOKEN_FILE")"
chmod 700 "$(dirname "$TOKEN_FILE")"
if [ -f "$TOKEN_FILE" ]; then
  chmod 600 "$TOKEN_FILE"
else
  echo "note: no $TOKEN_FILE yet; create it with:" >&2
  echo "  (umask 077; read -rs -p 'WORLD token: ' t; printf '%s\n' \"\$t\" > \"$TOKEN_FILE\")" >&2
fi

# Copy plist.
cp "$ROOT/${LABEL}.plist" "$LAUNCH_AGENTS/${LABEL}.plist"

# load the agent unless told not to.
if [ "${WORLD_AUTOLOAD:-1}" = "1" ]; then
  launchctl unload "$LAUNCH_AGENTS/${LABEL}.plist" 2>/dev/null || true
  launchctl load   "$LAUNCH_AGENTS/${LABEL}.plist"
fi

echo "installed:"
echo "  $LOCAL_BIN/track"
echo "  $LOCAL_BIN/world-push"
echo "  $LAUNCH_AGENTS/${LABEL}.plist"
