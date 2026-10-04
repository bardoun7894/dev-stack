#!/bin/bash
# audit.sh: zero-AI scan for rule problems. Prints only findings; "audit: clean" if none.
f=0; say(){ echo "$1"; f=1; }
L=~/.claude/logs/no-poll-guard.log
if [ -f "$L" ]; then n=$(awk -v d="$(date -v-1d +%F_%T)" '$1>d' "$L" | wc -l | tr -d ' ')
  [ "$n" -gt 0 ] && { say "HOOK: $n block(s) in 24h — check the last ones for false positives:"; tail -5 "$L" | cut -c1-200; }; fi
pgrep -f "board-astra/runqueue.sh" >/dev/null && say "OLD: runqueue.sh is running (retired path)"
ps -axo pid=,etime=,command= | grep -E "claude(-[0-9.]+)? -p .*dangerously-skip-permissions|versions/[0-9.]+ -p " | grep -v grep | awk '{print "OLD: claude -p worker pid " $1 " up " $2}' | while read l; do say "$l"; done
ps -axo pid=,command= | grep -E "node .*/jdelegate " | grep -v grep | grep -v -- "--no-auto-mcp" | awk '{print "HEAVY: jdelegate without lean flags, pid " $1}' | while read l; do say "$l"; done
for d in ~/.cache/board-astra ~/.cache/gate/*; do [ -d "$d" ] || continue
  for done in "$d"/gate-*.done; do [ -f "$done" ] || continue; [ "$(cat "$done")" = 0 ] && continue
    full=$(ls -t "$d"/full-*"$(basename "$done" .done | sed 's/^gate-//; s/-/_/g')"* 2>/dev/null | head -1)
    [ -n "$full" ] && ! grep -qE '^(FAILED|ERROR) |\[E\]|error:' "$full" && say "WASTED: $(basename "$done") failed with no failure names in its full output"
  done; done
db=$(PGPASSWORD=board timeout 5 /opt/homebrew/opt/postgresql@16/bin/psql -h localhost -U board -d postgres -Atc "select count(*) from pg_database where datname ~ '^board_(t|test|gq)_'" 2>/dev/null)
[ -n "$db" ] && [ "$db" -gt 15 ] && say "CLEANUP: $db leftover test databases on local Postgres"
s=$(cat ~/.claude/CLAUDE.md 2>/dev/null | wc -c | tr -d ' '); [ "$s" -gt 30000 ] && say "LOAD: global CLAUDE.md is ${s} bytes (>30 KB loads into every agent)"
[ $f = 0 ] && echo "audit: clean"
exit 0
