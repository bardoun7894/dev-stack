#!/bin/bash
# gaterun.sh <repo-root>: run queued gates, at most MAX_PARALLEL (from .gate.conf, default 1) at once.
# Queue file $S/gateq.txt, one line per job: "<name> <worktree-dir-name-or-abs-path>" (relative = <repo-root>/.worktrees/<x>).
# Writes $S/gate-<name>.log and $S/gate-<name>.done (exit code).
ROOT=$(cd "${1:?usage: gaterun.sh <repo-root>}" && pwd); REPO=$(basename "$ROOT")
S=$HOME/.cache/gate/$REPO; mkdir -p "$S"; echo "$ROOT" > "$S/root"; HERE=$(cd "$(dirname "$0")" && pwd); i=0
while true; do
  MAX=$( (MAX_PARALLEL=1; . "$ROOT/.gate.conf" >/dev/null 2>&1; echo "${MAX_PARALLEL:-1}") )
  if [ -s "$S/gateq.txt" ] && [ "$(jobs -rp | wc -l)" -lt "$MAX" ]; then
    read -r name wt < "$S/gateq.txt"; tail -n +2 "$S/gateq.txt" > "$S/gateq.tmp"; mv "$S/gateq.tmp" "$S/gateq.txt"
    [ -n "$name" ] || continue
    case $wt in /*) dir=$wt ;; *) dir=$ROOT/.worktrees/$wt ;; esac
    i=$((i+1)); rm -f "$S/.seen-gate-$name" "$S/gate-$name.done"
    ( bash "$HERE/gate.sh" "$dir" "$name" $(( (i % 4) + 1 )) > "$S/gate-$name.log" 2>&1; echo $? > "$S/gate-$name.done" ) &
  else sleep "${POLL:-30}"; fi
done
