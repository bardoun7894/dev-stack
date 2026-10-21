#!/usr/bin/env bash
# Self-contained test for bin/branch-lock and hooks/branch-lock-guard.sh in a throwaway repo.
set -u
HERE="$(cd "$(dirname "$0")/.." && pwd)"; BL="$HERE/bin/branch-lock"; GUARD="$HERE/hooks/branch-lock-guard.sh"
T="$(mktemp -d)"; export PATH="$HERE/bin:$PATH"; unset CLAUDECODE CLAUDE_CODE_ENTRYPOINT CODEX_HOME CODEX_SANDBOX CODEX_THREAD_ID BRANCH_LOCK_AGENT
pass=0; fail=0
ok() { if eval "$2"; then echo "PASS $1"; pass=$((pass+1)); else echo "FAIL $1"; fail=$((fail+1)); fi; }
cd "$T" && git init -q -b main repo && cd repo && git config user.email t@t && git config user.name t && git commit -q --allow-empty -m init
git worktree add -q -b feat ../wt2 main
ok "claim free"            '"$BL" claim feat --agent A >/dev/null'
ok "lock file in common"   '[ -f .git/agent-locks/feat.lock ]'
ok "reclaim own refreshes" '"$BL" claim feat --agent A | grep -q refreshed'
ok "other agent blocked"   '! "$BL" claim feat --agent B 2>/dev/null'
ok "check blocks B"        '! BRANCH_LOCK_AGENT=B "$BL" check feat 2>/dev/null'
ok "check ok for A"        'BRANCH_LOCK_AGENT=A "$BL" check feat'
ok "visible from worktree" '( cd ../wt2 && ! BRANCH_LOCK_AGENT=B "$BL" check 2>/dev/null )'
ok "ignore env bypass"     'BRANCH_LOCK_IGNORE=1 BRANCH_LOCK_AGENT=B "$BL" check feat 2>/dev/null'
ok "B cannot release"      '! "$BL" release feat --agent B 2>/dev/null'
ok "list shows lock"       '"$BL" list | grep -q "held by A"'
ok "A releases"            '"$BL" release feat --agent A | grep -q released'
ok "free after release"    '"$BL" status feat | grep -q free'
ok "stale takeover"        '"$BL" claim feat --agent A --ttl 0 >/dev/null && sleep 1 && "$BL" claim feat --agent B 2>/dev/null | grep -q claimed'
ok "B releases"            '"$BL" release feat --agent B >/dev/null'
ok "slash branch names"    '"$BL" claim chore/x --agent A >/dev/null && [ -f .git/agent-locks/chore__x.lock ]'
# default identity: kind + worktree
ok "default identity mine" '( cd ../wt2 && "$BL" claim >/dev/null && "$BL" check )'
ok "other kind blocked"    '( cd ../wt2 && ! CLAUDECODE=1 "$BL" check 2>/dev/null )'
# git hooks
git config core.hooksPath "$T/hooks"; mkdir -p "$T/hooks"; printf '#!/bin/sh\necho chained >/dev/null\n' > "$T/hooks/pre-commit"; chmod +x "$T/hooks/pre-commit"
ok "install-hook"          '"$BL" install-hook | grep -q added && grep -q "branch-lock guard" "$T/hooks/pre-commit" && grep -q chained "$T/hooks/pre-commit" && [ -x "$T/hooks/pre-push" ]'
ok "install-hook idempotent" '"$BL" install-hook | grep -q "^ok"'
ok "pre-commit blocks"     '( cd ../wt2 && echo x>f && git add f && ! CLAUDECODE=1 git commit -qm t 2>/dev/null )'
ok "detached check ok"     '( cd ../wt2 && git checkout -q --detach && CLAUDECODE=1 "$BL" check; rc=$?; git checkout -q feat; [ $rc = 0 ] )'
ok "pre-commit allows own" '( cd ../wt2 && git commit -qm t )'
# Claude hook
J() { printf '{"cwd":"%s","tool_input":{"command":"%s"}}' "$1" "$2"; }
ok "guard blocks commit"   '! J "$T/wt2" "git commit -m x" | CLAUDECODE=1 bash "$GUARD" 2>/dev/null'
ok "guard exit code 2"     'J "$T/wt2" "git push origin feat" | CLAUDECODE=1 bash "$GUARD" 2>/dev/null; [ $? = 2 ]'
ok "guard ignores status"  'J "$T/wt2" "git status" | CLAUDECODE=1 bash "$GUARD"'
ok "guard -C path"         '! J "$T" "git -C wt2 commit -m x" | CLAUDECODE=1 bash "$GUARD" 2>/dev/null'
ok "guard allows owner"    'J "$T/wt2" "git commit -m x" | bash "$GUARD"'
ok "guard non-repo"        'J "/" "git commit -m x" | bash "$GUARD"'
cd / && rm -rf "$T"
echo "passed=$pass failed=$fail"; [ "$fail" = 0 ]
