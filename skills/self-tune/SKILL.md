---
name: self-tune
description: Find and fix problems in Claude's own token/loop rules (TOKEN BUDGET in ~/.claude/CLAUDE.md, the no-poll-guard hook, brief templates, gate kit). Use on "self-tune", "fix your rules", "a rule blocked me", "the hook blocked a real command", or on your own when a hook blocks legitimate work, a worker wastes a capped run, a subagent sends "still running" wake-ups, a subagent pass exceeds ~250k tokens, or an old worker (claude -p, runqueue, heavy jdelegate) is found running.
---

# self-tune — fix your own rules, cheaply

The owner delegated this (2026-10-04): fix rule problems yourself, then report in one line. Scope is limited to: the TOKEN BUDGET section of `~/.claude/CLAUDE.md`, `~/.claude/hooks/no-poll-guard.sh`, the brief templates (`~/code/dev-stack/scripts/gate/brief-template.md`, project copies), and the gate kit (`~/code/dev-stack/scripts/gate/`). Never delete files; never touch anything outside that list without asking.

## 1. Detect (zero AI)

```bash
bash ~/.claude/skills/self-tune/scripts/audit.sh      # findings or "audit: clean"
bash ~/.claude/skills/self-tune/scripts/check-hook.sh # PASS 15/15 or the mismatches
```

Finding → fix:

| Finding | Fix |
|---|---|
| `HOOK:` a block that was legitimate work | Narrow the hook pattern (step 2) and add the case to `hooktest.sh` as `expect 0` |
| `OLD:` / `HEAVY:` process | Stop it if it is a worker of yours; tell the owner if it belongs to another session |
| `WASTED:` gate with no failure names | Make the step save full output (`tee $FULL`), never tail-only |
| `CLEANUP:` test DBs | List the `board_t_*`/`*_gw*` DBs you created and ask the owner to confirm before dropping any (never `board`, never `board_test` base DBs in use) |
| `LOAD:` CLAUDE.md > 30 KB | Move a rarely used section to `~/.claude/reference/` with a one-line pointer |
| Subagent "still running" wake-ups | Brief template: tests in the FOREGROUND |
| Subagent pass > 250k tokens | Brief was too wide: add exact files + line ranges, do-not-touch list |

## 2. Fix

1. Back up: `cp -p <file> ~/.claude/backups/$(date +%F)/`.
2. Edit with the smallest change. For the hook, write `no-poll-guard.sh.new` first.
3. Get the owner's approval before changing `no-poll-guard.sh`, `hooktest.sh` or `check-hook.sh` (they are a safety control and its test oracle; never edit the hook and its tests in the same unapproved run). Then test the hook: `HOOK_SUFFIX=.new bash scripts/hooktest.sh` then install with `mv`. Never put a blocked pattern literally in a live command: split it (`SL="sl""eep"`), the way `hooktest.sh` does, or the hook blocks your own test.
4. Run `check-hook.sh` again → must print `PASS n/n`.
5. If the rule text changed, update the TOKEN BUDGET section and the memory note `loops-in-scripts-not-ai`.

## 3. Report

One line to the owner: what broke, what changed, test result. Example:
`self-tune: hook blocked a heredoc brief that mentioned jdelegate → now ignores heredoc text; check-hook PASS 16/16.`
