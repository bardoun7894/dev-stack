#!/bin/bash
# gaterun.sh <repo-root>: run queued gates, at most MAX_PARALLEL (from .gate.conf, default 1) at once.
# Queue file $S/gateq.txt, one line per job: "<name> <worktree-dir-name-or-abs-path>" (relative = <repo-root>/.worktrees/<x>).
# Writes $S/gate-<name>.log and $S/gate-<name>.done (exit code).
ROOT=$(cd "${1:?usage: gaterun.sh <repo-root>}" && pwd); REPO=$(basename "$ROOT")
TIMEOUT_BIN=$(command -v timeout || command -v gtimeout)   # empty: no timeout(1) on this machine, gates run without a limit
S=$HOME/.cache/gate/$REPO; mkdir -p "$S"; echo "$ROOT" > "$S/root"; HERE=$(cd "$(dirname "$0")" && pwd); i=0
while true; do
  MAX=$( (MAX_PARALLEL=1; . "$ROOT/.gate.conf" >/dev/null 2>&1; echo "${MAX_PARALLEL:-1}") )
  if [ -s "$S/gateq.txt" ] && [ "$(jobs -rp | wc -l)" -lt "$MAX" ]; then
    read -r name wt < "$S/gateq.txt"; tail -n +2 "$S/gateq.txt" > "$S/gateq.tmp"; mv "$S/gateq.tmp" "$S/gateq.txt"
    [ -n "$name" ] || continue
    case $wt in /*) dir=$wt ;; *) dir=$ROOT/.worktrees/$wt ;; esac
    i=$((i+1)); rm -f "$S/.seen-gate-$name" "$S/gate-$name.done"
    # 2026-10-22: every gate run has a time limit (GATE_TIMEOUT from env or .gate.conf, default 45m); timeout(1)
    # kills the run's whole process group, so a hung test or leaked server cannot stall the queue. Exit 124 = timeout.
    TO=$( (GATE_TIMEOUT=${GATE_TIMEOUT:-45m}; . "$ROOT/.gate.conf" >/dev/null 2>&1; echo "${GATE_TIMEOUT:-45m}") )
    LIMIT=(); [ -n "$TIMEOUT_BIN" ] && LIMIT=("$TIMEOUT_BIN" -k 60 "$TO")
    ( { [ -n "$TIMEOUT_BIN" ] || echo "gaterun: no timeout(1) found, $name runs without a time limit"; } > "$S/gate-$name.log"
      "${LIMIT[@]}" bash "$HERE/gate.sh" "$dir" "$name" $(( (i % 4) + 1 )) >> "$S/gate-$name.log" 2>&1; rc=$?
      [ -n "$TIMEOUT_BIN" ] && [ $rc = 124 ] && echo "GATE TIMEOUT $name after $TO (killed)" >> "$S/gate-$name.log"; echo $rc > "$S/gate-$name.done" ) &
  else sleep "${POLL:-30}"; fi
done
