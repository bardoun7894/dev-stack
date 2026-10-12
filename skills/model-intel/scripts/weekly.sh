#!/usr/bin/env bash
# model-intel weekly run. Zero AI except one lean Haiku summary.
# fetch -> diff -> recommend -> propose/apply -> Haiku note -> KB copy -> notify.
# Exit: 0 ok, 1 fetch failed (nothing changed), 2 applied a router change.
# Env: MODEL_INTEL_DATA, MODEL_INTEL_TIERS, MODEL_INTEL_NO_APPLY=1 (propose only), MODEL_INTEL_NO_AI=1, MODEL_INTEL_NO_NOTIFY=1,
#      MODEL_INTEL_KB_DIR (default ~/code/dev-stack/ai-knowledge-base/raw/model-intel), MODEL_INTEL_CLAUDE (default claude)
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
SKILL="$(dirname "$HERE")"
export PATH="/opt/homebrew/bin:/usr/local/bin:/root/.local/bin:$HOME/.local/bin:/usr/bin:/bin:$PATH"
DATA="${MODEL_INTEL_DATA:-$SKILL/data}"
export MODEL_INTEL_DATA="$DATA"
DATE="${MODEL_INTEL_DATE:-$(date +%F)}"
export MODEL_INTEL_DATE="$DATE"
mkdir -p "$DATA/changes" "$DATA/proposals"
LOG="$DATA/weekly.log"
log() { printf '%s %s\n' "$(date '+%F %T')" "$*" >> "$LOG"; }
PY="python3 -I"

LOCK="$DATA/.weekly.lock"
if ! mkdir "$LOCK" 2>/dev/null; then
  # stale after 3h
  if [ -n "$(find "$LOCK" -maxdepth 0 -mmin +180 2>/dev/null)" ]; then rmdir "$LOCK"; mkdir "$LOCK" || exit 0; else log "already running"; exit 0; fi
fi
trap 'rmdir "$LOCK" 2>/dev/null' EXIT

log "start $DATE"
if ! $PY "$HERE/fetch.py" >> "$LOG" 2>&1; then
  log "fetch FAILED, nothing changed"
  [ "${MODEL_INTEL_NO_NOTIFY:-0}" = 1 ] || printf 'model-intel: weekly fetch FAILED %s (page format changed or network). Previous snapshot kept.\n' "$DATE" | bash "$HERE/notify.sh"
  exit 1
fi

$PY "$HERE/diff.py" > "$DATA/changes/$DATE-diff.md" 2>> "$LOG" || log "diff failed"
$PY "$HERE/recommend.py" >> "$LOG" 2>&1 || log "recommend failed"
$PY "$HERE/render_picks.py" >> "$LOG" 2>&1 || log "render_picks failed"
PROP_ARGS=""; [ "${MODEL_INTEL_NO_APPLY:-0}" = 1 ] && PROP_ARGS="--dry-run"
$PY "$HERE/propose_tiers.py" $PROP_ARGS >> "$LOG" 2>&1
PRC=$?
APPLIED=0; [ "$PRC" = 2 ] && APPLIED=1
case "$PRC" in 0|2) ;; *) log "propose_tiers rc=$PRC" ;; esac

# One Haiku call: <=150 word note. Lean: no hooks, no MCP, no tools, no CLAUDE.md, 60 s cap. Deterministic fallback.
NOTE="$DATA/changes/$DATE.md"
{
  echo "You write a short 'what changed this week' note (max 150 words, plain prose, no markdown headings, no emoji) for the owner of a multi-model router."
  echo "State: new models worth knowing, price or speed moves, and whether the router was changed. Use only the facts below."
  echo; echo "--- DIFF ---"; head -c 5000 "$DATA/changes/$DATE-diff.md"
  echo; echo "--- PROPOSALS ---"; head -c 3000 "$DATA/proposals/$DATE.md" 2>/dev/null
} > "$DATA/changes/.prompt.txt"
SUMMARY=""
if [ "${MODEL_INTEL_NO_AI:-0}" != 1 ]; then
  SUMMARY="$(CLAUDE_CODE_DISABLE_CLAUDE_MDS=1 timeout 60 "${MODEL_INTEL_CLAUDE:-claude}" -p --model haiku \
    --setting-sources project --settings '{"disableAllHooks":true,"autoMemoryEnabled":false,"attribution":{"commit":"","pr":""}}' \
    --strict-mcp-config --mcp-config '{"mcpServers":{}}' --tools "" \
    < "$DATA/changes/.prompt.txt" 2>> "$LOG" | head -c 1500)"
fi
if [ -z "$SUMMARY" ]; then
  log "haiku summary unavailable, using diff head"
  SUMMARY="$(grep -E '^## |^- (NEW|REMOVED|TOP)' "$DATA/changes/$DATE-diff.md" | head -12)"
  [ -n "$SUMMARY" ] || SUMMARY="First snapshot recorded ($(($(wc -l < "$DATA/latest/llm.csv") - 1)) LLM variants); comparison starts next week. See recommendations.md."
  [ "$APPLIED" = 1 ] && SUMMARY="$SUMMARY
Router changed: see proposals/$DATE.md (backup tiers.json.bak-model-intel-$DATE)."
fi
printf '# What changed (%s)\n\n%s\n' "$DATE" "$SUMMARY" > "$NOTE"

# KB article for kb-auto-compile
KB="${MODEL_INTEL_KB_DIR:-$HOME/code/dev-stack/ai-knowledge-base/raw/model-intel}"
if [ -d "$(dirname "$KB")" ] && [ -f "$DATA/recommendations.md" ]; then
  mkdir -p "$KB"
  { cat "$DATA/recommendations.md"; echo; cat "$NOTE"; [ -f "$DATA/proposals/$DATE.md" ] && { echo; cat "$DATA/proposals/$DATE.md"; }; } > "$KB/$DATE.md"
  log "kb article $KB/$DATE.md"
fi

[ "${MODEL_INTEL_NO_NOTIFY:-0}" = 1 ] || { printf 'model-intel %s\n%s\n' "$DATE" "$SUMMARY" | bash "$HERE/notify.sh"; }
log "done applied=$APPLIED"
[ "$APPLIED" = 1 ] && exit 2
exit 0
