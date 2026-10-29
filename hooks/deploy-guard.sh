#!/bin/bash
# deploy-guard.sh — PreToolUse Bash (G20). A deploy command runs only under an approved "Deploy it?" offer:
#   gate-run deploy-<p> ..., or bash/sh/source/./ of deploy.sh | dev-deploy.sh | deploy-*.sh | deploy_*.sh,
#   on the server directly, or inside `ssh <host> ...` from the Mac (a Mac command without ssh is not checked).
# Allowed with TOKYO_OFFER=<id> (command prefix or env) when `tokyo-deploy status <id>` says approved
# (and the project matches the deploy target, when the command shows one). Approved status cached 15 min.
# tokyo-deploy itself, read-only uses (cat/grep/sed -n/less, bash -n) and non-deploy commands pass without network.
# Status call failing or taking > 4 s denies. DEPLOY_GUARD_SKIP=1 in the command bypasses (owner emergencies).
# Source: dev-stack hooks/deploy-guard.sh, installed as a copy in ~/.claude/hooks/.
in=$(cat); cmd=$(jq -r '.tool_input.command // empty' <<<"$in")
[ -n "$cmd" ] || exit 0
printf '%s' "$cmd" | grep -qE 'deploy' || exit 0
os=${GATE_GUARD_UNAME:-$(uname -s)}
live=$(printf '%s\n' "$cmd" | awk '
  skip { if ($0 ~ "^[[:space:]]*" term "[\"'"'"']?[[:space:]]*$") skip=0; next }
  { print; if (match($0, /<<-?[[:space:]]*["'"'"']?[A-Za-z_][A-Za-z0-9_]*/)) { t=substr($0, RSTART, RLENGTH); gsub(/<<-?[[:space:]]*["'"'"']?/, "", t); term=t; skip=1 } }')
scan=$live
if printf '%s' "$live" | grep -qE '^[[:space:]]*(git[[:space:]]+commit|echo|tokyo-deploy)([[:space:]]|$)'; then
  scan=$(printf '%s\n' "$live" | sed -E "s/\"([^\"\\\\]|\\\\.)*\"//g; s/'[^']*'//g")
fi
if [ "$os" = Darwin ]; then
  printf '%s' "$scan" | grep -qE '(^|[^[:alnum:]_-])ssh[[:space:]]' || exit 0
fi

target=""; found=0; cdpath=""
is_script() { case ${1##*/} in deploy.sh|dev-deploy.sh|deploy-*.sh|deploy_*.sh) return 0;; esac; return 1; }
while IFS= read -r seg; do
  # shellcheck disable=SC2206
  toks=($(printf '%s' "$seg" | tr -d "\"'()\`"))
  n=${#toks[@]}; i=0
  # walk to the command word: skip VAR=val, sudo/env/time/nohup/exec, and `ssh [opts] host`
  while [ $i -lt $n ]; do
    case ${toks[$i]} in
      *=*|sudo|env|time|nohup|exec|command|nice) i=$((i+1)) ;;
      ssh)
        i=$((i+1))
        while [ $i -lt $n ]; do
          case ${toks[$i]} in
            -[oiplFJLRDEWbcem]) i=$((i+2)) ;;
            -*) i=$((i+1)) ;;
            *) i=$((i+1)); break ;;
          esac
        done ;;
      *) break ;;
    esac
  done
  [ $i -lt $n ] || continue
  w=${toks[$i]}; nx=${toks[$((i+1))]:-}
  case ${w##*/} in
    cd) cdpath=$nx ;;
    gate-run)
      case $nx in deploy-*) found=1; target=${nx#deploy-} ;; esac ;;
    bash|sh|zsh)
      j=$((i+1)); ro=0
      while [ $j -lt $n ]; do
        case ${toks[$j]} in -c) ro=1; break ;; -*n*) ro=1; j=$((j+1)) ;; -*) j=$((j+1)) ;; *) break ;; esac
      done
      [ $ro = 0 ] && [ $j -lt $n ] && is_script "${toks[$j]}" && found=1 ;;
    source|.)
      [ -n "$nx" ] && is_script "$nx" && found=1 ;;
    *)
      case $w in ./*|/*|*/*) is_script "$w" && found=1 ;; esac ;;
  esac
done < <(printf '%s\n' "$scan" | sed -E 's/(&&|\|\||;|\|)/\n/g')
[ $found = 1 ] || exit 0

printf '%s' "$cmd" | grep -qF 'DEPLOY_GUARD_SKIP=1' && { echo "deploy-guard: DEPLOY_GUARD_SKIP=1, G20 bypassed" >&2; exit 0; }

deny() {
  jq -n --arg r "$1" '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"deny",permissionDecisionReason:$r}}'
  exit 0
}
base="G20: no approved Deploy-it offer. Run tokyo-deploy ask <project> ... and wait for yes, or prefix TOKYO_OFFER=<id>."
id=$(printf '%s' "$cmd" | grep -oE '(^|[[:space:];&"'"'"'])TOKYO_OFFER=[A-Za-z0-9_-]+' | head -1 | sed -E 's/.*=//')
id=${id:-${TOKYO_OFFER:-}}
[ -n "$id" ] || deny "$base"
printf '%s' "$id" | grep -qE '^[A-Za-z0-9_-]+$' || deny "$base"

cache=${DEPLOY_GUARD_CACHE:-$HOME/.cache/deploy-guard}; mkdir -p "$cache" 2>/dev/null
cf="$cache/$id"; status=""
if [ -f "$cf" ] && [ -n "$(find "$cf" -mmin -15 2>/dev/null)" ]; then status=$(cat "$cf"); fi
if [ -z "$status" ]; then
  tmp=$(mktemp); tokyo-deploy status "$id" >"$tmp" 2>/dev/null & pid=$!
  for _ in $(seq 1 40); do kill -0 $pid 2>/dev/null || break; sleep 0.1; done
  if kill -0 $pid 2>/dev/null; then kill $pid 2>/dev/null; rm -f "$tmp"; deny "$base (status check for $id timed out)"; fi
  wait $pid; rc=$?; status=$(head -1 "$tmp"); rm -f "$tmp"
  [ $rc = 0 ] && [ -n "$status" ] || deny "$base (status check for $id failed)"
  set -- $status
  [ "${2:-}" = approved ] || deny "$base (offer $id is ${2:-unknown})"
  printf '%s\n' "$status" >"$cf"
fi
set -- $status
[ "${2:-}" = approved ] || deny "$base (offer $id is ${2:-unknown})"
proj=${1:-}
if [ -n "$proj" ] && [ "$proj" != "?" ]; then
  if [ -n "$target" ]; then
    case $target in "$proj"|"$proj"-*) ;; *) deny "$base (offer $id is for $proj, command deploys $target)" ;; esac
  elif [ -n "${cdpath:-}" ]; then
    case $cdpath in *"$proj"*) ;; *) deny "$base (offer $id is for $proj, command runs in $cdpath)" ;; esac
  fi
fi
exit 0
