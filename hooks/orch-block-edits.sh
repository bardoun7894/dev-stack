#!/bin/bash
# PreToolUse: in orchestrator mode (CLAUDE_ORCH=1, set by the claude() wrapper
# when claude runs inside herdr) the main session delegates through jdelegate:
# no direct file edits, and no built-in Agent subagents (they run hidden inside
# the session on a model Jev did not pick; jdelegate workers get a herdr tab).
# Any other session is untouched. jdelegate's workers unset CLAUDE_ORCH.
[ "${CLAUDE_ORCH:-}" = "1" ] || exit 0
# Kill switch: owner turned off worker delegation (touch/rm ~/.claude/orch-off).
[ -f "$HOME/.claude/orch-off" ] && exit 0
input=$(cat)
tool=$(printf '%s' "$input" | jq -r '.tool_name // ""' 2>/dev/null)
# Write/Edit stay allowed in Claude's own scratchpad and auto-memory dir (nowhere else); ".." is never accepted.
case "$tool" in
  Write|Edit|MultiEdit|NotebookEdit)
    fp=$(printf '%s' "$input" | jq -r '.tool_input.file_path // .tool_input.notebook_path // ""' 2>/dev/null)
    case "$fp" in
      *..*) ;;
      /private/tmp/claude-*/*/scratchpad/*|/tmp/claude-*/*/scratchpad/*|"$HOME"/.claude/projects/*/memory/*) exit 0 ;;
    esac ;;
esac
case "$tool" in
  Agent|Task)
    reason='Orchestrator mode: do not use the built-in Agent tool. Run the job as a worker with: jdelegate --cwd <repo> --name <label> "<self-contained brief>" (Bash; run_in_background for parallel/long jobs). Jev picks the model and it opens in its own herdr tab.' ;;
  *)
    reason='Orchestrator mode: do not edit files yourself. Delegate the change with: jdelegate --cwd <repo> --name <label> "<self-contained brief: goal, files, exact change, done-when, what to report>" (Bash; run_in_background for long or parallel jobs), then check the result.' ;;
esac
jq -nc --arg r "$reason" '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"deny",permissionDecisionReason:$r}}'
