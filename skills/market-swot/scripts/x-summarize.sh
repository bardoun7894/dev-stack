#!/usr/bin/env bash
# skills/market-swot/scripts/x-summarize.sh <posts.md>
# Summarize collected X posts with Grok on Command Code via pi. Grok has NO live X search:
# it may only summarize the posts inlined in the prompt. Exit 3 "grok unavailable" on failure/empty.
set -u
F="${1:-}"
if [ -z "$F" ] || [ ! -f "$F" ]; then echo "usage: $0 <posts.md>" >&2; exit 2; fi
posts="$(cat "$F")"
prompt="You have NO live X/Twitter search. Summarize ONLY the posts below; do not add outside knowledge or invent posts.
Output: 3-6 themes about current UI/UX and AI-design practice. For each theme: one sentence and the post URLs that support it (URLs exactly as given, nothing else). Skip themes without a post URL.

POSTS:
$posts"
out="$(pi -p --no-session --no-tools --model commandcode/xai/grok-4.7 "$prompt" </dev/null 2>/dev/null)"; rc=$?
if [ "$rc" -ne 0 ] || [ -z "$(printf '%s' "$out" | tr -d '[:space:]')" ]; then
  echo "grok unavailable" >&2
  exit 3
fi
printf '%s\n' "$out"
