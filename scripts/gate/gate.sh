#!/bin/bash
# gate.sh <worktree> <name> [slot]: zero-AI project gate driven by <repo-root>/.gate.conf (see README.md).
# One line per step: "STEP <part>:<step> PASS|FAIL <tail>". Exit 0 pass, 1 fail, 3 infra down, 4 merge conflict.
set -o pipefail
W=$1; NAME=$2; N=${3:-1}
[ -d "$W" ] && [ -n "$NAME" ] || { echo "usage: gate.sh <worktree> <name> [slot]" >&2; exit 2; }
W=$(cd "$W" && pwd)
ROOT=$(cd "$W" && cd "$(git rev-parse --git-common-dir)" && cd .. && pwd)
REPO=$(basename "$ROOT"); S=$HOME/.cache/gate/$REPO; mkdir -p "$S"
CONF=$ROOT/.gate.conf
[ -f "$CONF" ] || { echo "no .gate.conf in $ROOT" >&2; exit 2; }
MAIN=main
# shellcheck disable=SC1090
. "$CONF"
FULL=$S/full-$NAME.txt; : > "$FULL"
DB=${REPO//[^A-Za-z0-9]/_}_gq_${NAME//[^A-Za-z0-9]/_}_$(date +%H%M)
export GATE_WT=$W GATE_NAME=$NAME GATE_DB=$DB GATE_N=$N GATE_REPO=$REPO GATE_ROOT=$ROOT
set -f; for kv in $ENV; do kv=${kv//\{DB\}/$DB}; kv=${kv//\{N\}/$N}; export "$kv"; done; set +f

# test the branch as it would land: merge current main first; a conflict stops here
if git -C "$W" symbolic-ref -q HEAD >/dev/null; then
  git -C "$W" merge -q --no-edit "$MAIN" >/dev/null 2>&1 || { git -C "$W" merge --abort; echo "CONFLICT with main (gate not run)"; exit 4; }
  echo "merged main $(git -C "$W" rev-parse --short "$MAIN")"
fi
CH=$(git -C "$W" diff --name-only "$MAIN"...HEAD 2>/dev/null)

TMP=$S/.step-$NAME.$$; trap 'rm -f "$TMP"' EXIT
ANYFAIL=0; INFRA=0

# step <part> <label> <dir> <cmd> [is-test]
step() {
  local part=$1 label=$2 dir=$3 cmd=$4 istest=$5 rc ok tail
  ( cd "$dir" && eval "$cmd" ) >"$TMP" 2>&1 </dev/null; rc=$?
  if [ $rc -ne 0 ] && [ -n "$RIF" ] && grep -qE "$RIF" "$TMP"; then
    [ -n "$RCL" ] && ( cd "$dir" && eval "$RCL" ) >/dev/null 2>&1 </dev/null
    ( cd "$dir" && eval "$cmd" ) >"$TMP" 2>&1 </dev/null; rc=$?
  fi
  ok=1; [ $rc -eq 0 ] || ok=0
  if [ $ok = 1 ] && [ "$istest" = 1 ] && [ -n "$PASSRE" ]; then tail -n 3 "$TMP" | grep -qE "$PASSRE" || ok=0; fi
  tail=$(grep -v '^[[:space:]]*$' "$TMP" | tail -n 1 | tr -d '\r' | cut -c1-160)
  if [ $ok = 1 ]; then echo "STEP $part:$label PASS $tail"; [ "$istest" = 1 ] && cat "$TMP" >> "$FULL"
  else echo "STEP $part:$label FAIL rc=$rc $tail"; cat "$TMP" >> "$FULL"; ANYFAIL=1; fi
  return $((1 - ok))
}
# lines <multiline-string> -> "name|cmd" pairs run via step
runlist() { local part=$1 dir=$2 list=$3 line; while IFS= read -r line; do [ -n "${line// }" ] || continue; step "$part" "${line%%|*}" "$dir" "${line#*|}"; done <<< "$list"; }

echo "scope: from $MAIN diff ($(printf '%s' "$CH" | grep -c .) files)"
for P in $PARTS; do
  v() { local x="${P}_$1"; printf '%s' "${!x}"; }
  PATHS=$(v PATHS); PRE=$(v PRE); TEST=$(v TEST); PASSRE=$(v PASS); RIF=$(v RETRY_IF); RCL=$(v RETRY_CLEAN); DIR=$(v DIR)
  D=$W; [ -n "$DIR" ] && D=$W/$DIR
  if [ -n "$CH" ] && [ -n "$PATHS" ] && ! printf '%s\n' "$CH" | grep -qE "$PATHS"; then echo "STEP $P:skipped PASS (no diff vs $MAIN)"; continue; fi
  if [ -n "$PRE" ]; then step "$P" pre "$W" "$PRE" || { INFRA=1; echo "INFRA DOWN: $P (part not run)"; continue; }; fi
  runlist "$P" "$D" "$(v SETUP)"
  [ -n "$TEST" ] && step "$P" test "$D" "$TEST" 1
  RIF_SAVE=$RIF; PASSRE=
  runlist "$P" "$D" "$(v CHECKS)"; RIF=$RIF_SAVE
done
RIF=; RCL=; PASSRE=
runlist guard "$W" "$GUARDS"
if [ $INFRA = 1 ]; then echo "GATE FAIL $NAME (infra)"; exit 3; fi
[ $ANYFAIL = 0 ] && { echo "GATE PASS $NAME"; exit 0; }
echo "GATE FAIL $NAME"; exit 1
