#!/bin/bash
# bash tests/test_orch_block_edits.sh — orch-block-edits.sh allows Write/Edit only in the scratchpad and auto-memory dir
HOOK=${HOOK:-$(cd "$(dirname "$0")/.." && pwd)/hooks/orch-block-edits.sh}
fail=0
# Isolated HOME: the hook honours $HOME/.claude/orch-off (owner kill switch), which must not leak into the test.
REAL_HOME=$HOME; HOME=$(mktemp -d); trap 'rm -rf "$HOME"' EXIT
run() { # tool path -> prints deny|allow
  out=$(jq -nc --arg t "$1" --arg p "$2" '{tool_name:$t,tool_input:{file_path:$p}}' | CLAUDE_ORCH=1 bash "$HOOK")
  [ -n "$out" ] && echo deny || echo allow
}
check() { got=$(run "$2" "$3"); [ "$got" = "$1" ] || { echo "FAIL expected $1 got $got: $2 $3"; fail=1; }; }
check allow Write /private/tmp/claude-501/-Users-x-code-y/abc-123/scratchpad/notes.md
check allow Edit  /private/tmp/claude-501/-Users-x-code-y/abc-123/scratchpad/sub/a.txt
check allow Write "$HOME/.claude/projects/-Users-x-code-y/memory/MEMORY.md"
check allow Edit  "$HOME/.claude/projects/-Users-x-code-y/memory/feedback_a.md"
check deny  Write "/Users/x/code/dev-stack/bin/jdelegate"
check deny  Edit  /private/tmp/claude-501/-Users-x-code-y/abc-123/other/a.txt
check deny  Write "$HOME/.claude/projects/-Users-x-code-y/foo.md"
check deny  Write "$HOME/.claude/settings.json"
check deny  Write /private/tmp/claude-501/x/y/scratchpad/../../../../../../etc/passwd
check deny  Write "$HOME/.claude/projects/-Users-x/memory/../../../settings.json"
check deny  Agent ""
[ $fail = 0 ] && echo "all ok"
exit $fail
