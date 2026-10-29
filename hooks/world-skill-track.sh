#!/bin/bash
# world-skill-track.sh: Claude Code PostToolUse hook for the "Skill" tool. Records each skill use in the world feed with
# `track add --kind skill`. Fire-and-forget: background, 3 s cap, no output, always exits 0. WORLD_TRACK=0 disables it.
#
# Wiring (NOT applied; add to ~/.claude/settings.json by hand):
#   "hooks": { "PostToolUse": [ { "matcher": "Skill",
#     "hooks": [ { "type": "command", "command": "bash $HOME/code/dev-stack/hooks/world-skill-track.sh" } ] } ] }

input=$(cat 2>/dev/null)
[ "${WORLD_TRACK:-1}" = "0" ] && exit 0
command -v track >/dev/null 2>&1 || exit 0
command -v jq >/dev/null 2>&1 || exit 0

fields=$(printf '%s' "$input" | jq -r '[(.tool_input.skill // .tool_input.name // ""), (.cwd // ""), (.session_id // "")] | @tsv' 2>/dev/null) || exit 0
IFS=$'\t' read -r name cwd session <<<"$fields"
[ -n "$name" ] || exit 0
project=$(basename "${cwd:-unknown}")

to=""
command -v timeout >/dev/null 2>&1 && to="timeout 3"
[ -z "$to" ] && command -v gtimeout >/dev/null 2>&1 && to="gtimeout 3"
( $to track add --kind skill --status done --project "$project" --title "skill $name" --ref "$name" \
    --source live --key "skill:${name}:${session}:$(date +%s)" >/dev/null 2>&1 </dev/null & ) >/dev/null 2>&1
exit 0
