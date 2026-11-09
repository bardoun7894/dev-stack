#!/bin/bash
# gaterun.sh <repo-root>: run queued gates, at most MAX_PARALLEL (from .gate.conf, default 1) at once.
# Queue file $S/gateq.txt, one line per job: "<name> <worktree-dir-name-or-abs-path>" (relative = <repo-root>/.worktrees/<x>).
# Writes $S/gate-<name>.log and $S/gate-<name>.done (exit code).
ROOT=$(cd "${1:?usage: gaterun.sh <repo-root>}" && pwd); REPO=$(basename "$ROOT")
# empty: no timeout(1) on this machine, gates run without a limit (GATERUN_TIMEOUT_BIN overrides, "" = none, for tests)
TIMEOUT_BIN=${GATERUN_TIMEOUT_BIN-$(command -v timeout || command -v gtimeout)}
ENV_TIMEOUT=${GATE_TIMEOUT:-}; KILL_AFTER=${GATE_KILL_AFTER:-60}
S=$HOME/.cache/gate/$REPO; mkdir -p "$S"; echo "$ROOT" > "$S/root"; HERE=$(cd "$(dirname "$0")" && pwd); i=0
while true; do
  MAX=$( (MAX_PARALLEL=1; . "$ROOT/.gate.conf" >/dev/null 2>&1; echo "${MAX_PARALLEL:-1}") )
  if [ -s "$S/gateq.txt" ] && [ "$(jobs -rp | wc -l)" -lt "$MAX" ]; then
    read -r name wt < "$S/gateq.txt"; tail -n +2 "$S/gateq.txt" > "$S/gateq.tmp"; mv "$S/gateq.tmp" "$S/gateq.txt"
    [ -n "$name" ] || continue
    case $wt in /*) dir=$wt ;; *) dir=$ROOT/.worktrees/$wt ;; esac
    i=$((i+1)); rm -f "$S/.seen-gate-$name" "$S/gate-$name.done"
    # 2026-10-22: every gate run has a time limit (env GATE_TIMEOUT, else .gate.conf, else 45m); timeout(1) kills the
    # run's process group (TERM, then KILL after GATE_KILL_AFTER s), so a hung test or leaked server cannot stall the queue.
    TO=${ENV_TIMEOUT:-$( (GATE_TIMEOUT=; . "$ROOT/.gate.conf" >/dev/null 2>&1; echo "${GATE_TIMEOUT:-45m}") )}
    note=""; case $TO in ''|*[!0-9smhd.]*|*.*.*) note="gaterun: bad GATE_TIMEOUT '$TO', using 45m"; TO=45m ;; esac
    LIMIT=(); [ -n "$TIMEOUT_BIN" ] && LIMIT=("$TIMEOUT_BIN" --verbose -k "$KILL_AFTER" "$TO")
    ( { [ -n "$note" ] && echo "$note"; [ -n "$TIMEOUT_BIN" ] || echo "gaterun: no timeout(1) found, $name runs without a time limit"; } > "$S/gate-$name.log"
      ${LIMIT[@]+"${LIMIT[@]}"} bash "$HERE/gate.sh" "$dir" "$name" $(( (i % 4) + 1 )) >> "$S/gate-$name.log" 2>&1; rc=$?
      # only timeout's own --verbose line marks a timeout: a gate that exits 124 itself is not one; 137 = KILL after TERM
      case $rc in 124|137) grep -q "sending signal" "$S/gate-$name.log" && echo "GATE TIMEOUT $name after $TO (killed)" >> "$S/gate-$name.log" ;; esac
      echo $rc > "$S/gate-$name.done" ) &
  else sleep "${POLL:-30}"; fi
done
