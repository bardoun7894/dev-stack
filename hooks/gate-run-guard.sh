#!/bin/bash
# gate-run-guard.sh — PreToolUse Bash (G5/G6). Heavy commands must be wrapped in `gate-run <project> <dur> -- <cmd>`:
#   - on the Mac: when the command runs on `ssh MyContabo`
#   - on the server: always (anything that is not the Mac)
# Quoted text is only ignored for git commit / echo (like no-poll-guard); heredoc bodies are always ignored.
# GATE_SKIP=1 in the command bypasses. Source: dev-stack hooks/gate-run-guard.sh, installed as a copy in ~/.claude/hooks/.
in=$(cat); cmd=$(jq -r '.tool_input.command // empty' <<<"$in")
[ -n "$cmd" ] || exit 0
printf '%s' "$cmd" | grep -qF 'GATE_SKIP=1' && exit 0
os=${GATE_GUARD_UNAME:-$(uname -s)}
live=$(printf '%s\n' "$cmd" | awk '
  skip { if ($0 ~ "^[[:space:]]*" term "[[:space:]]*$") skip=0; next }
  { print; if (match($0, /<<-?[[:space:]]*["'"'"']?[A-Za-z_][A-Za-z0-9_]*/)) { t=substr($0, RSTART, RLENGTH); gsub(/<<-?[[:space:]]*["'"'"']?/, "", t); term=t; skip=1 } }')
scan=$live
if printf '%s' "$live" | grep -qE '^[[:space:]]*(git[[:space:]]+commit|echo)([[:space:]]|$)'; then
  scan=$(printf '%s\n' "$live" | sed -E "s/\"([^\"\\\\]|\\\\.)*\"//g; s/'[^']*'//g")
fi
if [ "$os" = Darwin ]; then
  printf '%s' "$scan" | grep -qE 'ssh[^|;&]*MyContabo' || exit 0
  scan=$(printf '%s\n' "$scan" | sed -E 's/.*ssh[^|;&]*MyContabo//')
fi
heavy='(^|[^[:alnum:]_-])(pnpm[[:space:]]+build|npm[[:space:]]+run[[:space:]]+build|next[[:space:]]+build|playwright[[:space:]]+test|ops/test\.sh)'
is_heavy() { # one segment
  local seg=$1 rest
  printf '%s' "$seg" | grep -qE "$heavy" && return 0
  if printf '%s' "$seg" | grep -qE '(^|[^[:alnum:]_.-])pest([[:space:]"'"'"']|$)'; then printf '%s' "$seg" | grep -qF -- '--filter' || return 0; fi
  if printf '%s' "$seg" | grep -qE 'vitest[[:space:]]+run'; then
    rest=${seg#*vitest run}; printf '%s' "$rest" | grep -qE '[^[:space:]]*(/|\.[cm]?[tj]sx?)' || return 0
  fi
  if printf '%s' "$seg" | grep -qE '(^|[^[:alnum:]_.-])pytest([[:space:]"'"'"']|$)'; then
    rest=${seg#*pytest}; printf '%s' "$rest" | grep -qE '(^|[[:space:]])[^[:space:]-][^[:space:]]*(/|\.py|::)' || return 0
  fi
  return 1
}
while IFS= read -r seg; do
  is_heavy "$seg" || continue
  printf '%s' "$seg" | grep -qE 'gate-run[[:space:]]+[^[:space:]].*[[:space:]]--[[:space:]]' && continue
  echo "BLOCKED by gate-run-guard: heavy command outside the gate queue. Wrap it: gate-run <project> <duration> -- <cmd>, e.g. ssh MyContabo \"cd /root/x && gate-run x 45m -- pnpm build\". GATE_SKIP=1 bypasses." >&2
  exit 2
done < <(printf '%s\n' "$scan" | sed -E 's/(&&|\|\||;|\|)/\n/g')
exit 0
