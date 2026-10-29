#!/usr/bin/env bash
# skills/finish-apps/scripts/triage.sh <active.json>
# Adds completeness (jev score) and next_action (jev choice) to each project. Env JEV_BIN (default jev).
# Exit 2/3 or confidence < 0.7 on the choice -> next_action="needs-llm" (never a pass).
set -u
IN="${1:-}"
[ -n "$IN" ] && [ -f "$IN" ] || { echo "usage: $0 <active.json>" >&2; exit 2; }
JEV="${JEV_BIN:-jev}"
MIN=0.7

out="[]"
while IFS= read -r p; do
  completeness=null; next='"needs-llm"'
  if r="$("$JEV" score "How finished is this app for production?" "0 skeleton" "1 core flows missing" \
        "2 core flows work, gaps remain" "3 feature-complete, polish/defects left" "4 production-ready" \
        --log finish-apps -s "$p" 2>/dev/null)"; then
    completeness="$(printf '%s' "$r" | jq -c '.score // null' 2>/dev/null || echo null)"
  fi
  if r="$("$JEV" choice "What should happen next for this app?" \
        write-specs="no specs or specs lack plan/tasks" fix-defects="failing tests, open defect tasks" \
        implement-open-tasks="specs ready with open tasks" \
        research-features="unclear feature set, needs competitor/SWOT research" \
        verdict="looks done, needs readiness verdict" \
        --log finish-apps -s "$p" --min "$MIN" 2>/dev/null)"; then
    next="$(printf '%s' "$r" | jq -c '.choice // "needs-llm"' 2>/dev/null || echo '"needs-llm"')"
  fi
  out="$(printf '%s' "$out" | jq --argjson p "$p" --argjson c "${completeness:-null}" --argjson n "$next" \
    '. + [$p + {completeness:$c, next_action:$n} + (if $p.customer then {report_only:true} else {} end)]')"
done < <(jq -c '.[]' "$IN")

printf '%s' "$out" | jq 'group_by(.last_commit) | reverse | map(sort_by(.completeness // -1)) | add // []'
