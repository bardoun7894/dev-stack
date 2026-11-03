#!/usr/bin/env bash
# Claude Code PreToolUse hook (matcher: Bash). Blocks `git commit` / `git push` when another agent
# holds a fresh branch-lock on the current branch (see dev-stack/bin/branch-lock). Fail-open on any error.
input="$(cat 2>/dev/null || true)"
command -v branch-lock >/dev/null 2>&1 || exit 0
command -v jq >/dev/null 2>&1 || exit 0
cmd="$(printf '%s' "$input" | jq -r '.tool_input.command // empty' 2>/dev/null)"
cwd="$(printf '%s' "$input" | jq -r '.cwd // empty' 2>/dev/null)"
printf '%s' "$cmd" | grep -Eq '(^|[;&|[:space:]])git([[:space:]]+-C[[:space:]]+[^[:space:]]+)?[[:space:]]+(commit|push)([[:space:]]|$)' || exit 0
dir="$cwd"
gc="$(printf '%s' "$cmd" | sed -nE 's/.*git[[:space:]]+-C[[:space:]]+([^[:space:]]+).*/\1/p' | head -1)"
[ -n "$gc" ] && case "$gc" in /*) dir="$gc" ;; *) dir="$cwd/$gc" ;; esac
[ -n "$dir" ] && [ -d "$dir" ] || exit 0
cd "$dir" 2>/dev/null || exit 0
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || exit 0
msg="$(branch-lock check 2>&1 >/dev/null)"; rc=$?
if [ "$rc" = 1 ]; then
  echo "$msg" >&2
  echo "Another agent holds this branch. Do not commit/push here: use your own branch/worktree, or wait. Check with: branch-lock status" >&2
  exit 2
fi
exit 0
