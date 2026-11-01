#!/bin/bash
# deploy-guard.sh — PreToolUse Bash (G20). A deploy command runs only under an approved "Deploy it?" offer:
#   gate-run deploy-<p> ..., or bash/sh/source/./ of deploy.sh | dev-deploy.sh | deploy-*.sh | deploy_*.sh,
#   on the server directly, or inside `ssh <host> ...` from the Mac.
# Allowed with TOKYO_OFFER=<id> (command prefix or env) when `tokyo-deploy status <id>` says approved
# (and the deploy path, resolved from cd or the hook cwd, is inside the project, matched by whole path component).
# Approved status cached 15 min.
# tokyo-deploy itself, read-only uses (cat/grep/sed -n/less, bash -n) and non-deploy commands pass without network.
# Status call failing or taking > 4 s denies. DEPLOY_GUARD_SKIP=1 in the hook's own environment bypasses (owner emergencies).
# Source: dev-stack hooks/deploy-guard.sh, installed as a copy in ~/.claude/hooks/.
set -f
in=$(cat)
command -v jq >/dev/null || { echo "deploy-guard: jq not found, G20 cannot check" >&2; exit 2; }
if ! cmd=$(jq -r '.tool_input.command // empty' <<<"$in" 2>/dev/null); then cmd=$in; fi
cwd=$(jq -r '.cwd // empty' <<<"$in" 2>/dev/null)
[ -n "$cmd" ] || exit 0
printf '%s' "$cmd" | tr -d "\"'\\\\" | grep -qiE 'deploy|[*?[]' || exit 0
live=$(printf '%s\n' "$cmd" | awk '
  skip { if ($0 ~ "^[[:space:]]*" term "[\"'"'"']?[[:space:]]*$") skip=0; next }
  { print; if ($0 !~ /<<</ && $0 ~ /(^|[^[:alnum:]_-])(cat|tee|python3|git)([[:space:]]|$)/ &&$0 !~ /(^|[[:space:];&|(])(bash|sh|zsh)([[:space:]]|$)|[[:space:]]-s([[:space:]]|$)/ && match($0, /<<-?[[:space:]]*["'"'"']?[A-Za-z_][A-Za-z0-9_]*/)) { t=substr($0, RSTART, RLENGTH); gsub(/<<-?[[:space:]]*["'"'"']?/, "", t); term=t; skip=1 } }')
scan=$live
if printf '%s' "$live" | grep -qE '^[[:space:]]*(git[[:space:]]+commit|echo|tokyo-deploy)([[:space:]]|$)'; then
  scan=$(printf '%s\n' "$live" | sed -E "s/\"([^\"\\\\\$\`]|\\\\.)*\"//g; s/'[^']*'//g")
fi

targets=""; found=0; cdpath=""; spaths=""; unk=0
is_script() { # a deploy script name, or a glob in the basename that could expand to one; $var is not a name
  local b c; b=$(printf '%s' "${1##*/}" | tr A-Z a-z)
  case $b in deploy.sh|dev-deploy.sh|deploy-*.sh|deploy_*.sh) return 0;; esac
  case $b in *\$*) return 1;; *[\*\?\[]*) for c in deploy.sh dev-deploy.sh deploy-x.sh deploy_x.sh; do [[ $c == $b ]] && return 0; done;; esac
  return 1
}
while IFS= read -r seg; do
  # shellcheck disable=SC2206
  toks=($(printf '%s' "$seg" | tr -d "\"'()\`\\\\"))
  n=${#toks[@]}; i=0
  # walk to the command word: skip VAR=val, sudo/env/time/nohup/exec, wrappers and their flags/numbers, and `ssh [opts] host`
  while [ $i -lt $n ]; do
    case ${toks[$i]} in
      sudo|env|nice|timeout)
        i=$((i+1))
        while [ $i -lt $n ]; do
          case ${toks[$i]} in -[ugskn]|-C|-U|-h|-p|-r|-t) i=$((i+2)) ;; *) break ;; esac
        done ;;
      *=*|time|nohup|exec|command|setsid|flock|stdbuf|xargs|-*|[0-9]*|if|then|else|do|while|until|'{'|'!') i=$((i+1)) ;;
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
      case $nx in deploy-*) found=1; targets+="${nx#deploy-}"$'\n' ;; esac ;;
    eval) found=1; unk=1 ;;
    python3|python|node|make|npm|pnpm|yarn)
      for ((k=i+1; k<n; k++)); do case $(printf '%s' "${toks[$k]}" | tr A-Z a-z) in *deploy*) found=1; unk=1 ;; esac; done ;;
    bash|sh|zsh)
      j=$((i+1)); ro=0; c=0
      while [ $j -lt $n ]; do
        case ${toks[$j]} in -*c*) c=1; j=$((j+1)); break ;; -*n*) ro=1; j=$((j+1)) ;; -*) j=$((j+1)) ;; *) break ;; esac
      done
      if [ $c = 1 ]; then
        for ((k=j; k<n; k++)); do is_script "${toks[$k]}" && { found=1; spaths+="${toks[$k]}"$'\n'; }; done
      elif [ $ro = 0 ] && [ $j -lt $n ] && is_script "${toks[$j]}"; then
        found=1; spaths+="${toks[$j]}"$'\n'
      fi ;;
    source|.)
      [ -n "$nx" ] && is_script "$nx" && { found=1; spaths+="$nx"$'\n'; } ;;
    *)
      case $w in ./*|/*|*/*) is_script "$w" && { found=1; spaths+="$w"$'\n'; } ;; esac ;;
  esac
done < <(printf '%s\n' "$scan" | sed -E 's/(&|\|\||;|\||\$\(|`)/\n/g')
[ $found = 1 ] || exit 0

[ "${DEPLOY_GUARD_SKIP:-}" = 1 ] && { echo "deploy-guard: DEPLOY_GUARD_SKIP=1, G20 bypassed" >&2; exit 0; }

deny() {
  jq -n --arg r "$1" '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"deny",permissionDecisionReason:$r}}'
  exit 0
}
base="G20: no approved Deploy-it offer. Run tokyo-deploy ask <project> ... and wait for yes, or prefix TOKYO_OFFER=<id>."
id=$(printf '%s' "$cmd" | grep -oE '(^|[[:space:];&"'"'"'])TOKYO_OFFER=[A-Za-z0-9_-]+' | head -1 | sed -E 's/.*=//')
id=${id:-${TOKYO_OFFER:-}}
[ -n "$id" ] || deny "$base"
printf '%s' "$id" | grep -qE '^[A-Za-z0-9_-]+$' || deny "$base"

[ $unk = 0 ] || deny "$base (command runs a deploy through eval/an interpreter, which cannot be checked)"
status=""
if [ -z "$status" ]; then
  tmp=$(mktemp); tokyo-deploy status "$id" >"$tmp" 2>/dev/null & pid=$!
  for _ in $(seq 1 40); do kill -0 $pid 2>/dev/null || break; sleep 0.1; done
  if kill -0 $pid 2>/dev/null; then kill $pid 2>/dev/null; rm -f "$tmp"; deny "$base (status check for $id timed out)"; fi
  wait $pid; rc=$?; status=$(head -1 "$tmp"); rm -f "$tmp"
  [ $rc = 0 ] && [ -n "$status" ] || deny "$base (status check for $id failed)"
  set -- $status
  [ "${2:-}" = approved ] || deny "$base (offer $id is ${2:-unknown})"
fi
set -- $status
[ "${2:-}" = approved ] || deny "$base (offer $id is ${2:-unknown})"
proj=${1:-}
[ -n "$proj" ] && [ "$proj" != "?" ] || deny "$base (offer $id has no project)"
# Is the script inside project $proj? Yes when under /root/<proj> or $HOME/<proj> (any letter case, because
# offer ids are lowercase and repos may not be), or in a real git worktree of that repo. Errors mean no.
in_project() {
  local f=$1 r d common ok=1
  shopt -s nocasematch
  for r in "/root/$proj" "$HOME/$proj"; do
    case "$f/" in "$r/"*) ok=0 ;; esac
  done
  d=${f%/*}
  if [ $ok != 0 ] && [ -d "$d" ]; then
    common=$(git -C "$d" rev-parse --path-format=absolute --git-common-dir 2>/dev/null)
    for r in "/root/$proj" "$HOME/$proj"; do
      case "$common" in "$r/.git") ok=0 ;; esac
    done
  fi
  shopt -u nocasematch
  return $ok
}
if [ -n "$proj" ] && [ "$proj" != "?" ]; then
  while IFS= read -r target; do
    [ -n "$target" ] || continue
    case $target in "$proj"|"$proj"-*) ;; *) deny "$base (offer $id is for $proj, command deploys $target)" ;; esac
  done <<<"$targets"
  while IFS= read -r spath; do
    [ -n "$spath" ] || continue
    base_dir=${cdpath:-$cwd}; case $base_dir in /*|"") ;; *) base_dir=${cwd:+$cwd/}$base_dir ;; esac
    case $spath in /*) full=$spath ;; *) full=${base_dir:+$base_dir/}$spath ;; esac
    case $full in /*) ;; *) deny "$base (offer $id is for $proj, cannot tell where $spath runs)" ;; esac
    case $full in */../*|*/..) deny "$base (offer $id is for $proj, command deploys $full)" ;; esac
    in_project "$full" || deny "$base (offer $id is for $proj, command deploys $full)"
  done <<<"$spaths"
fi
exit 0
