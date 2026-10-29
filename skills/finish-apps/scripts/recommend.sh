#!/usr/bin/env bash
# skills/finish-apps/scripts/recommend.sh <triage.json> [--top N]
# Per project: ranked spec suggestions R1..RN. Evidence is deterministic; ONE LLM call per project
# (retry once on invalid JSON); Jev scores impact and drops duplicates; ranking is in jq.
# Env: FINISH_APPS_LLM (default "claude -p --model sonnet --output-format text"), JEV_BIN (default jev).
set -u
IN=""; TOP=3
while [ $# -gt 0 ]; do
  case "$1" in
    --top) TOP="${2:-}"; shift 2 ;;
    -*) echo "usage: $0 <triage.json> [--top N]" >&2; exit 2 ;;
    *) IN="$1"; shift ;;
  esac
done
[ -n "$IN" ] && [ -f "$IN" ] || { echo "usage: $0 <triage.json> [--top N]" >&2; exit 2; }
case "$TOP" in ''|*[!0-9]*) echo "bad --top" >&2; exit 2 ;; esac
JEV="${JEV_BIN:-jev}"
LLM="${FINISH_APPS_LLM:-claude -p --model sonnet --output-format text}"
HERE="$(cd "$(dirname "$0")" && pwd)"
INV="$HERE/../../readiness-audit/scripts/inventory.sh"
CAP=24000
DUP_MAX=0.6

section() { # title file maxlines maxchars
  [ -f "$2" ] || return 0
  printf '\n=== %s ===\n' "$1"; head -n "$3" "$2" | head -c "$4"; echo
}
newest() { # dir glob...  -> newest matching file
  local d="$1"; shift
  find "$d" -maxdepth 3 -type f \( "$@" \) -not -path '*/node_modules/*' -not -path '*/.git/*' 2>/dev/null \
    | sort | tail -1
}

bundle() { # path -> evidence text on stdout
  local p="$1" inv f a
  inv="$(bash "$INV" "$p" 2>/dev/null)" || inv='{}'
  echo "=== inventory ==="
  printf '%s' "$inv" | jq -c '{git,signals,stubs}' 2>/dev/null
  echo "=== spec dirs (id has_spec has_plan has_tasks open done) ==="
  printf '%s' "$inv" | jq -r '.specs[]? | "specs/\(.id) spec=\(.has_spec) plan=\(.has_plan) tasks=\(.has_tasks) open=\(.open) done=\(.done)"' 2>/dev/null
  echo "=== specs missing plan.md or tasks.md ==="
  printf '%s' "$inv" | jq -r '.specs[]? | select(.has_plan==false or .has_tasks==false) | "specs/\(.id)"' 2>/dev/null
  echo "=== TODO/FIXME count: $(printf '%s' "$inv" | jq -r '.stubs // 0' 2>/dev/null) ==="
  for f in $(printf '%s' "$inv" | jq -r '.prd[]?' 2>/dev/null | head -5); do
    section "PRD $f" "$p/$f" 200 5000
  done
  a="$(ls -d "$p"/specs/_audit/*/ 2>/dev/null | sort | tail -1)"
  [ -n "$a" ] && section "audit ${a#$p/}research.md" "${a}research.md" 300 6000
  f="$(newest "$p" -name 'READINESS-AUDIT-*.md')"; [ -n "$f" ] && section "audit ${f#$p/}" "$f" 300 6000
  f="$(newest "$p" -iname '*swot*.md')"; [ -n "$f" ] && section "swot ${f#$p/}" "$f" 300 6000
}

prompt() { # name bundle
  cat <<P
You recommend which specs to write next for one software project. Use ONLY the evidence below.
PROJECT: $1

Reply with strict JSON only (no prose, no code fence): an array of up to 6 candidates
[{"title":"...","kind":"new-feature|fix-defects|complete-spec|polish|research","why":"<=2 sentences",
  "evidence":["relative file path or spec dir that appears in the evidence"],"size":"S|M|L"}]

EVIDENCE:
$2
P
}

# parse LLM text -> JSON array of candidates, or fail
parse() {
  local t="$1" j
  j="$(printf '%s' "$t" | jq -c 'if type=="array" then . elif type=="object" then (.candidates // empty) else empty end' 2>/dev/null)"
  if [ -z "$j" ]; then
    j="$(printf '%s\n' "$t" | grep -v '^[[:space:]]*```' | jq -c 'if type=="array" then . elif type=="object" then (.candidates // empty) else empty end' 2>/dev/null)"
  fi
  [ -n "$j" ] && printf '%s' "$j" | jq -e 'type=="array"' >/dev/null 2>&1 && printf '%s' "$j"
}

out="[]"
while IFS= read -r proj; do
  name="$(printf '%s' "$proj" | jq -r .name)"
  path="$(printf '%s' "$proj" | jq -r '.path // ""')"
  rep="$(printf '%s' "$proj" | jq -c '(.report_only // .customer // false) | if . then {report_only:true} else {} end')"
  if [ -z "$path" ] || [ ! -d "$path" ]; then
    out="$(printf '%s' "$out" | jq --arg n "$name" '. + [{name:$n, skipped:"other-host", recommendations:[]}]')"
    continue
  fi
  ev="$(bundle "$path" | head -c "$CAP")"
  pr="$(prompt "$name" "$ev")"
  cands=""; err=""
  for attempt in 1 2; do
    raw="$(printf '%s' "$pr" | eval "$LLM" 2>/dev/null)"
    if cands="$(parse "$raw")"; then err=""; break; fi
    cands=""; err="llm returned invalid JSON"
  done
  if [ -z "$cands" ]; then
    out="$(printf '%s' "$out" | jq --arg n "$name" --arg e "$err" --argjson r "$rep" '. + [{name:$n, recommendations:[], error:$e} + $r]')"
    continue
  fi

  specs="$(find "$path/specs" -mindepth 1 -maxdepth 1 -type d -not -name '_*' -exec basename {} \; 2>/dev/null | sort | jq -R . | jq -sc .)"
  kept="[]"
  while IFS= read -r c; do
    # shape + evidence paths must exist inside the project
    ok=true
    printf '%s' "$c" | jq -e '(.title|type=="string") and (.kind|IN("new-feature","fix-defects","complete-spec","polish","research")) and (.size|IN("S","M","L")) and (.evidence|type=="array" and length>0)' >/dev/null 2>&1 || ok=false
    if $ok; then
      while IFS= read -r ev_p; do
        case "$ev_p" in /*|*..*|"") ok=false; break ;; esac
        [ -e "$path/$ev_p" ] || { ok=false; break; }
      done < <(printf '%s' "$c" | jq -r '.evidence[] | tostring')
    fi
    $ok || continue
    cs="$(printf '%s' "$c" | jq -c '{title,kind,why,size}')"
    if [ "$(printf '%s' "$specs" | jq length)" -gt 0 ]; then
      dstate="$(jq -nc --argjson c "$cs" --argjson s "$specs" '{candidate:$c, existing_specs:$s}')"
      if d="$("$JEV" noul "This candidate duplicates a spec that already exists" -s "$dstate" --log finish-apps-recommend 2>/dev/null)"; then
        pdup="$(printf '%s' "$d" | jq -r '.noul // 0' 2>/dev/null || echo 0)"
        awk -v p="$pdup" -v m="$DUP_MAX" 'BEGIN{exit !(p+0>m+0)}' && continue
      fi
    fi
    impact=null; conf=null
    if r="$("$JEV" score "How much does this spec move the app toward production for real users?" \
         "0 none" "1 minor" "2 useful" "3 important" "4 blocking launch" \
         -s "$cs" --log finish-apps-recommend 2>/dev/null)"; then
      impact="$(printf '%s' "$r" | jq -c '.score // null' 2>/dev/null || echo null)"
      conf="$(printf '%s' "$r" | jq -c '.confidence // null' 2>/dev/null || echo null)"
    fi
    kept="$(printf '%s' "$kept" | jq --argjson c "$c" --argjson i "${impact:-null}" --argjson k "${conf:-null}" \
      '. + [$c + {impact:$i, impact_confidence:$k}]')"
  done < <(printf '%s' "$cands" | jq -c '.[]')

  recs="$(printf '%s' "$kept" | jq -c --argjson top "$TOP" '
    sort_by([-(.impact // -1), ({"S":0,"M":1,"L":2}[.size])]) | .[:$top]
    | to_entries | map(.value + {code:"R\(.key+1)"}
      | {code,title,kind,why,evidence,size,impact,impact_confidence})')"
  out="$(printf '%s' "$out" | jq --arg n "$name" --argjson r "$recs" --argjson rep "$rep" \
    '. + [{name:$n, recommendations:$r} + $rep]')"
done < <(jq -c '.[]' "$IN")

printf '%s\n' "$out" | jq .
