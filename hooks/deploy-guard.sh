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
  skip { if ($0 ~ "^[[:space:]]*" term "[[:space:]]*$") skip=0; next }
  { print; if (match($0, /<<-?[[:space:]]*["'"'"']?[A-Za-z_][A-Za-z0-9_]*/)) { t=substr($0, RSTART, RLENGTH); gsub(/<<-?[[:space:]]*["'"'"']?/, "", t); term=t; skip=1 } }')
scan=$live
if printf '%s' "$live" | grep -qE '^[[:space:]]*(git[[:space:]]+commit|echo|tokyo-deploy)([[:space:]]|$)'; then
  scan=$(printf '%s\n' "$live" | sed -E "s/\"([^\"\\\\]|\\\\.)*\"//g; s/'[^']*'//g")
fi
if [ "$os" = Darwin ]; then
  printf '%s' "$scan" | grep -qE '(^|[^[:alnum:]_-])ssh[[:space:]]' || exit 0
fi

target=""; found=0
while IFS= read -r seg; do
  # shellcheck disable=SC2206
  toks=($(printf '%s' "$seg" | tr -d "\"'()\`" ))
  n=${#toks[@]}; i=0
  while [ $i -lt $n ]; do
    t=${toks[$i]}; p=""; [ $i -gt 0 ] && p=${toks[$((i-1))]}
    case $t in
      deploy-*) if [ "$p" = gate-run ] || [ "${toks[$((i-2))]:-}" = gate-run ]; then found=1; target=${t#deploy-}; fi ;;
    esac
    case ${t##*/} in
      deploy.sh|dev-deploy.sh|deploy-*.sh|deploy_*.sh)
        j=$((i-1)); ro=0
        while [ $j -ge 0 ] && case ${toks[$j]} in -*) true;; *) false;; esac; do
          case ${toks[$j]} in -*n*) ro=1;; esac; j=$((j-1))
        done
        w=""; [ $j -ge 0 ] && w=${toks[$j]}
        if [ $ro = 0 ]; then
          case $w in
            bash|sh|zsh|source|.|*/bash|*/sh) found=1 ;;
            cat|grep|egrep|rg|sed|less|more|head|tail|bat|wc|ls|stat|diff|file|shellcheck|vim|nano|nl|awk|cp|mv|rm|chmod|git|scp|rsync) ;;
            *) case $t in ./*|/*)
                 k=0; rd=0
                 while [ $k -lt $i ]; do
                   case ${toks[$k]} in cat|grep|egrep|rg|sed|less|more|head|tail|bat|wc|ls|stat|diff|file|shellcheck|vim|nano|nl|awk|cp|mv|rm|chmod|git|scp|rsync|echo) rd=1;; esac
                   k=$((k+1))
                 done
                 [ $rd = 0 ] && found=1 ;; esac ;;
          esac
        fi ;;
      cd) [ $((i+1)) -lt $n ] && cdpath=${toks[$((i+1))]} ;;
    esac
    i=$((i+1))
  done
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
