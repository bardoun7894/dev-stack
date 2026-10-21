---
name: branch-lock
description: Claim a git branch before editing it and release it when done, so concurrent agents (Claude, Codex, Gemini, OpenCode, pi, Kimi, bots) never edit, commit or push the same branch at once. Use at the start and end of any task that changes files in a repo.
---

# branch-lock

Many agents work on the same repos at once. A branch is owned by one agent at a time.

1. Before the first edit: `branch-lock claim [<branch>] --note "<task>"`.
   - Exit 1 = BUSY: another agent holds it. Do not edit that checkout. Create your own branch in a new
     worktree (`git worktree add -b <new-branch> ../<repo>-<task> <default-branch>`) and claim that.
2. Long task: re-run `branch-lock claim` about every hour (heartbeat). Locks go stale after 2h.
3. When done (committed, or abandoned): `branch-lock release`.
4. See holders: `branch-lock status` / `branch-lock list`.

Never use `--force` or `BRANCH_LOCK_IGNORE=1` without the owner's OK.
Set a stable name with `--agent <name>` or `BRANCH_LOCK_AGENT` if several sessions share one checkout.
Locks are local to this Mac (stored in the repo's git common dir); they do not cover the MyContabo bot.
Guards: a Claude Code PreToolUse hook blocks `git commit`/`git push` on a branch someone else holds;
`branch-lock install-hook` adds the same guard as git pre-commit/pre-push hooks for one repo.
