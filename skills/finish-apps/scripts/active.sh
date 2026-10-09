#!/usr/bin/env bash
# skills/finish-apps/scripts/active.sh [--days N] [--host mac|server|all]
# Zero AI. JSON array of repos with commits in the last N days (default 7), Mac + MyContabo.
# Env: FINISH_APPS_MAC_ROOTS, FINISH_APPS_SERVER_ROOTS (space-separated globs),
#      FINISH_APPS_SSH_HOST (default MyContabo; empty = skip server).
# Internal: --scan-local --label L --roots "globs"  (runs on the server via ssh, prints local entries).
set -u

DAYS=7; HOSTSEL=all; SCAN_LOCAL=0; LABEL=mac; ROOTS=""
while [ $# -gt 0 ]; do
  case "$1" in
    --days) DAYS="$2"; shift 2 ;;
    --host) HOSTSEL="$2"; shift 2 ;;
    --scan-local) SCAN_LOCAL=1; shift ;;
    --label) LABEL="$2"; shift 2 ;;
    --roots) ROOTS="$2"; shift 2 ;;
    *) echo "usage: $0 [--days N] [--host mac|server|all]" >&2; exit 2 ;;
  esac
done
case "$DAYS" in ''|*[!0-9]*) echo "bad --days" >&2; exit 2 ;; esac

norm_remote() { # git@github.com:Owner/Repo.git -> github.com/owner/repo
  printf '%s' "$1" | tr 'A-Z' 'a-z' | sed -E 's#^[a-z+]+://##; s#^[^@/]+@##; s#:#/#; s#\.git/?$##; s#/$##'
}

scan_local() { # prints JSON array of entries for ROOTS, host=LABEL
  local seen="" out="[]" g d common remote n last cnt nspec mp mt ot item
  for g in $ROOTS; do
    for d in $g; do
      [ -d "$d" ] && [ -d "$d/.git" ] || continue          # linked worktrees have .git as a file
      common="$(cd "$d" && git rev-parse --path-format=absolute --git-common-dir 2>/dev/null)" || continue
      case "
$seen
" in *"
$common
"*) continue ;; esac
      seen="$seen
$common"
      cnt="$(git -C "$d" log --all --since="$DAYS days ago" --format=%ct 2>/dev/null | sort -rn)"
      [ -n "$cnt" ] || continue
      n="$(printf '%s\n' "$cnt" | wc -l | tr -d ' ')"
      last="$(printf '%s\n' "$cnt" | head -1)"
      remote="$(norm_remote "$(git -C "$d" remote get-url origin 2>/dev/null || true)")"
      nspec=0; mp=0; mt=0; ot=0
      if [ -d "$d/specs" ]; then
        for s in "$d"/specs/*/; do
          [ -d "$s" ] || continue
          nspec=$((nspec+1))
          [ -f "$s/plan.md" ] || mp=$((mp+1))
          if [ -f "$s/tasks.md" ]; then
            ot=$((ot + $(grep -cE '^[[:space:]]*- \[ \]' "$s/tasks.md" 2>/dev/null || true)))
          else mt=$((mt+1)); fi
        done
      fi
      item="$(jq -n --arg name "$(basename "$d")" --arg host "$LABEL" --arg path "$d" \
        --argjson commits "$n" --argjson last "$last" --arg remote "$remote" \
        --argjson st "$nspec" --argjson mp "$mp" --argjson mt "$mt" --argjson ot "$ot" \
        '{name:$name,host:$host,path:$path,also_at:[],commits:$commits,last_commit:($last|todate),
          remote:$remote,specs_total:$st,specs_missing_plan:$mp,specs_missing_tasks:$mt,open_tasks:$ot}')"
      out="$(printf '%s' "$out" | jq --argjson i "$item" '. + [$i]')"
    done
  done
  printf '%s\n' "$out"
}

if [ "$SCAN_LOCAL" = 1 ]; then scan_local; exit 0; fi

HERE="$(cd "$(dirname "$0")" && pwd)"
MAC_ROOTS="${FINISH_APPS_MAC_ROOTS-$HOME/projects/*}"
SRV_ROOTS="${FINISH_APPS_SERVER_ROOTS-/root/projects/* /root/* /opt/* /var/www/*}"
SSH_HOST="${FINISH_APPS_SSH_HOST-MyContabo}"

all="[]"
if [ "$HOSTSEL" = mac ] || [ "$HOSTSEL" = all ]; then
  ROOTS="$MAC_ROOTS"; LABEL=mac
  all="$(scan_local)"
fi
if { [ "$HOSTSEL" = server ] || [ "$HOSTSEL" = all ]; } && [ -n "$SSH_HOST" ]; then
  if srv="$(ssh -o ConnectTimeout=8 -o BatchMode=yes "$SSH_HOST" bash -s -- --scan-local --days "$DAYS" \
        --label server --roots "'$SRV_ROOTS'" < "$0" 2>/dev/null)" && printf '%s' "$srv" | jq -e 'type=="array"' >/dev/null 2>&1; then
    all="$(jq -n --argjson a "$all" --argjson b "$srv" '$a + $b')"
  else
    echo "warn: server $SSH_HOST unreachable or scan failed; continuing with Mac results" >&2
  fi
fi

# dedupe by normalized remote: keep most commits, other paths go to also_at
cust="$HERE/../config/customers.txt"
custjson="$(grep -vE '^[[:space:]]*(#|$)' "$cust" 2>/dev/null | jq -R . | jq -s . 2>/dev/null || echo '[]')"
printf '%s' "$all" | jq --argjson cust "$custjson" '
  (map(select(.remote != "")) | group_by(.remote)
    | map(sort_by(-.commits) as $g | $g[0] + {also_at: ($g[1:] | map(.host + ":" + .path))})) as $withr
  | ($withr + map(select(.remote == "")))
  | map(. + {customer: (.name as $n | $cust | index($n) != null)})
  | sort_by(.last_commit) | reverse'
