#!/bin/bash
# failsum.sh <lines-file>: 3-line diagnosis of gate failure lines.
# Chain (tested 2026-10-04): opencode-go deepseek flash (cheap paid, ~11s) -> glm flash -> Claude Haiku (no setting sources, no MCP).
# OpenCode *free* models refuse CLI use ("free tier can only be used from within OpenCode"); claude --bare is not logged in.
# Hard cases skip the cheap model (not reliable there): >5 failure lines, timeouts/hangs, Gradle/compile errors, merge conflicts.
if [ $(wc -l < "$1") -gt 5 ] || grep -qE "Timeout|rc=143|What went wrong|^e: |error:|CONFLICT|INFRA" "$1"; then echo "HARD: $(wc -l < "$1" | tr -d " ") failure line(s) — Opus triage, Sonnet subagent fixes (cheap model skipped)"; exit 0; fi
[ -s "$1" ] || exit 0
P="Gate failure lines from a Flutter+FastAPI repo are below. In at most 3 short lines: likely cause (test bug, code bug, infra, flaky) and the first file to look at. No preamble.
$(head -c 6000 "$1")"
for m in opencode-go/deepseek-v4.1-flash opencode-go/glm-5.3-flash; do
  out=$(cd /tmp && timeout 90 opencode run -m $m "$P" </dev/null 2>/dev/null | grep -v -e WARN -e '^\s*$' | tail -4)
  [ -n "$out" ] && ! echo "$out" | grep -q '^Error' && { echo "[$m]"; echo "$out"; exit 0; }
done
out=$(echo "$P" | (cd /tmp && timeout 90 claude -p --model claude-haiku-4-5-20251001 --strict-mcp-config --setting-sources "") 2>/dev/null | tail -4)
[ -n "$out" ] && { echo "[haiku]"; echo "$out"; } || echo "(no summary model answered; read the lines above)"
