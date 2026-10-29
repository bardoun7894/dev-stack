#!/usr/bin/env bash
# skills/market-swot/scripts/freshness.sh [file...]
# Zero-AI. For each file prints {file,last_refreshed,age_days,stale}. stale = age_days > FRESH_MAX_DAYS (default 7).
# Missing stamp => stale:true. Default files: references/uiux-motion.md references/sources.md.
set -u
command -v jq >/dev/null || { echo "jq required" >&2; exit 1; }
HERE="$(cd "$(dirname "$0")" && pwd)"
MAX="${FRESH_MAX_DAYS:-7}"
[ "$#" -eq 0 ] && set -- "$HERE/../references/uiux-motion.md" "$HERE/../references/sources.md"
to_epoch() { date -j -f %F "$1" +%s 2>/dev/null || date -d "$1" +%s 2>/dev/null; }
now="$(date +%s)"
for f in "$@"; do
  stamp=""
  [ -f "$f" ] && stamp="$(grep -m1 -E '^last_refreshed:[[:space:]]*[0-9]{4}-[0-9]{2}-[0-9]{2}' "$f" | sed -E 's/^last_refreshed:[[:space:]]*//' | cut -c1-10)"
  age=""
  [ -n "$stamp" ] && e="$(to_epoch "$stamp")" && [ -n "$e" ] && age=$(( (now - e) / 86400 ))
  jq -n --arg file "$f" --arg stamp "$stamp" --arg age "$age" --argjson max "$MAX" \
    '{file:$file,last_refreshed:(if $stamp=="" then null else $stamp end),age_days:(if $age=="" then null else ($age|tonumber) end)} | .stale = (if .age_days==null then true else .age_days > $max end)'
done | jq -s .
