#!/bin/bash
# bash tests/test_commit_msg_hook.sh — commit-msg hook (G10) rejects attribution lines, accepts clean messages
HOOK="$(cd "$(dirname "$0")/.." && pwd)/scripts/githooks/commit-msg"
T=$(mktemp -d); fails=0
check() { # name expected-rc message
  printf '%b' "$3" > "$T/m"; "$HOOK" "$T/m" >/dev/null 2>&1; rc=$?
  [ "$rc" = "$2" ] && echo "ok   $1" || { echo "FAIL $1 (rc=$rc, want $2)"; fails=1; }
}
check clean 0 "feat: add thing\n\nbody\n"
check coauthor 1 "feat: x\n\nCo-Authored-By: Claude <noreply@anthropic.com>\n"
check coauthor-lowercase 1 "feat: x\n\nco-authored-by: Bot <b@x>\n"
check generated 1 "feat: x\n\nGenerated with [Claude Code](https://claude.com)\n"
check mention-in-prose 0 "docs: explain the Co-Authored-By rule\n"
check comment-line 0 "feat: x\n# Co-Authored-By: Claude <n@a>\n# Generated with Claude Code\n"
check scissors 0 "feat: x\n\n# ------------------------ >8 ------------------------\n+Co-Authored-By: a <a@b>\n+Generated with Claude Code\n"
check subject-mention 0 "fix: block Generated with Claude Code\n"
check emoji-generated 1 "feat: x\n\n🤖 Generated with [Claude Code](https://claude.com)\n"
ALLOW_COAUTHOR=1 check bypass 0 "x\n\nCo-Authored-By: Human <h@x>\n"
rm -rf "$T"; exit $fails
