#!/bin/bash
# monitor.sh [repo-name...]: zero-AI watcher. Exits on the FIRST event: PASS, FAIL (with failing steps + names), or STALL.
# Repos default to every dir under ~/.cache/gate/. A finished gate (gate-<n>.done) fires once (.seen-gate-<n>).
G=$HOME/.cache/gate; HERE=$(cd "$(dirname "$0")" && pwd); STALL_SECS=${STALL_SECS:-1800}; POLL=${POLL:-60}
mtime() { stat -f %m "$1" 2>/dev/null || stat -c %Y "$1"; }
[ $# -gt 0 ] && REPOS=("$@") || { REPOS=(); for d in "$G"/*/; do [ -d "$d" ] && REPOS+=("$(basename "$d")"); done; }
while true; do
  for r in "${REPOS[@]}"; do D=$G/$r
    for f in "$D"/gate-*.done; do [ -f "$f" ] || continue; n=$(basename "$f" .done); [ ! -f "$D/.seen-$n" ] || continue
      touch "$D/.seen-$n"; L=$D/$n.log; rc=$(cat "$f"); name=${n#gate-}
      bad=$(grep -E '^STEP .* FAIL|CONFLICT|INFRA DOWN' "$L")
      if [ "$rc" = 0 ] && [ -z "$bad" ]; then echo "PASS $r/$name: $(grep -c '^STEP .* PASS' "$L") steps"; grep -E '^STEP ' "$L" | cut -c1-120; exit 0; fi
      echo "FAIL $r/$name (exit $rc)"; echo "$bad"
      full=$D/full-$name.txt
      if [ -f "$full" ]; then grep -E '^(FAILED|ERROR) |\[E\]$|^e: |error:|What went wrong' "$full" | cut -c1-200 | sort -u | head -12 | tee "$D/.faillines"; fi
      echo "$bad" | grep -E 'CONFLICT|INFRA' >> "$D/.faillines"
      echo "-- free-model summary:"; [ -f "$D/.faillines" ] && bash "$HERE/failsum.sh" "$D/.faillines"; rm -f "$D/.faillines"
      exit 0; done
    if pgrep -f "gate/gate.sh" >/dev/null; then lf=$(ls -t "$D"/full-*.txt "$D"/gate-*.log 2>/dev/null | head -1)
      [ -n "$lf" ] && [ $(( $(date +%s) - $(mtime "$lf") )) -gt "$STALL_SECS" ] && { echo "STALL: $r/$(basename "$lf") unchanged ${STALL_SECS}s+"; exit 0; }; fi
  done
  sleep "$POLL"
done
