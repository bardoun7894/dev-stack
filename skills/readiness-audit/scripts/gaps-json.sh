#!/usr/bin/env bash
# skills/readiness-audit/scripts/gaps-json.sh <gap-report.md> <out.json>
# Zero AI. Parses the Findings table (| Code | Source | Severity | Evidence | ...) into
# [{code,text,severity,source?}]. text = Evidence column. Severity words map to P0..P3
# (see references/gap-report-template.md); a row with no recognised severity is an error.
set -u
[ $# -eq 2 ] && [ -f "$1" ] || { echo "usage: $0 <gap-report.md> <out.json>" >&2; exit 2; }
command -v jq >/dev/null || { echo "jq not installed" >&2; exit 1; }

rows="$(awk -F'|' '/^[[:space:]]*\|[[:space:]]*G[0-9]+[[:space:]]*\|/ {
  for (i = 2; i <= 5; i++) { gsub(/^[[:space:]]+|[[:space:]]+$/, "", $i) }
  printf "%s\t%s\t%s\t%s\n", $2, $3, $4, $5 }' "$1")"

out="[]"
while IFS=$'\t' read -r code source sev text; do
  [ -n "$code" ] || continue
  case "$(printf '%s' "$sev" | tr 'A-Z' 'a-z')" in
    p0|critical|blocker|blocks*) sev=P0 ;;
    p1|high|major|must*)         sev=P1 ;;
    p2|medium|moderate|should*)  sev=P2 ;;
    p3|low|minor|nit)            sev=P3 ;;
    *) echo "gaps-json: $code has no recognised severity" >&2; exit 1 ;;
  esac
  out="$(printf '%s' "$out" | jq --arg c "$code" --arg t "$text" --arg s "$sev" --arg src "$source" \
    '. + [{code:$c,text:$t,severity:$s} + (if $src != "" then {source:$src} else {} end)]')" || exit 1
done <<< "$rows"
printf '%s\n' "$out" > "$2"
