---
name: team-mode
description: Commit dev-stack into the current project's `.claude/` so teammates get the same skills + hooks + model routing automatically. Sets up an hourly auto-update check that pulls from the dev-stack remote (throttled, network-failure-safe, silent). Triggers on "enable team mode", "share dev-stack with teammates", "commit the stack", "/team-mode". One-shot per project — idempotent on re-run.
allowed-tools: Bash Read Write Edit
---

# team-mode — dev-stack for teammates via committed `.claude/`

The global dev-stack install lives under `~/.claude/` and only works for the current user. team-mode bridges it to a team by:

1. Committing a minimal `.claude/` into the current project root
2. Wiring a SessionStart hook that syncs from the global dev-stack once/hour
3. Updating the project's `CLAUDE.md` to reference the dev-stack ruleset
4. Adding one row to README so teammates know what they're opting into

## Preconditions

- Current cwd is inside a git repo (walk up to find `.git/`).
- Global dev-stack is installed at `~/code/dev-stack/` (check for `scripts/refresh-rule.sh`).
- `~/code/dev-stack` has a remote (`origin`) teammates can reach — if it's your private fork, teammates must have read access.

Fail-fast if any precondition misses. Print what's missing and stop.

## Mode: `required` vs `optional`

Single argument, defaults to `optional`:

- **`required`** — teammates who don't have dev-stack installed get a hard warning at session start: "This repo requires dev-stack. Install with `git clone <remote> ~/code/dev-stack && ~/code/dev-stack/install.sh`."
- **`optional`** — teammates get a soft notice once and session continues.

## What it creates

```
<project-root>/
  .claude/
    settings.local.json   ← committed (auto-update hook + ruleset pointer)
    CLAUDE.md.team        ← committed (team-specific rules)
    hooks/
      session-start-sync.sh ← committed (one-hour-throttled sync)
  CLAUDE.md               ← appended: reference to dev-stack ruleset
  README.md               ← appended: "Install dev-stack to contribute" row
```

Nothing else is copied. The actual skills/agents stay in each teammate's `~/.claude/` via the global install — team-mode does not vendor the skills into the repo.

## Steps

1. **Verify preconditions** (above). Stop on fail.
2. **Create `.claude/`** in project root with the files listed above.
3. **Write `settings.local.json`** with the SessionStart hook calling `hooks/session-start-sync.sh`.
4. **Write `hooks/session-start-sync.sh`:**
   ```bash
   #!/usr/bin/env bash
   # Dev-stack auto-sync — once per hour, silent on network failure.
   set -eo pipefail
   STAMP="$HOME/.claude/.dev-stack-last-sync"
   [ -f "$STAMP" ] && [ $(($(date +%s) - $(date -r "$STAMP" +%s))) -lt 3600 ] && exit 0
   (cd "$HOME/code/dev-stack" && git pull --quiet --ff-only) 2>/dev/null || true
   touch "$STAMP"
   ```
5. **Append a one-liner to project's `CLAUDE.md`**: "This project uses dev-stack (`~/code/dev-stack`). See `.claude/CLAUDE.md.team` for project rules that extend the global ruleset."
6. **Write `.claude/CLAUDE.md.team`** with placeholders for project-specific rules (ports, deploy commands, auth quirks). User edits it later.
7. **Append to `README.md`:**
   ```
   ## Contributing with AI
   This repo uses [dev-stack](<remote>). Install once:
       git clone <remote> ~/code/dev-stack && ~/code/dev-stack/install.sh
   Then all teammates get the same skills, hooks, and model routing.
   ```
8. **Commit the `.claude/` folder** and the CLAUDE.md/README changes with a single commit: `"require dev-stack for AI-assisted work"` (or `"nudge teammates to use dev-stack"` for `optional` mode).

## Rules

- **Never commit secrets.** `.claude/settings.local.json` must not contain API keys, tokens, or private paths. If any are in the user's global `~/.claude/settings.json`, strip them before writing.
- **Never overwrite an existing `.claude/`.** If `.claude/settings.local.json` already exists, merge keys — don't replace.
- **Never force-push.** Use a feature branch if the project's main is protected.
- **Never push teammates' machines to update.** Auto-sync is client-side and throttled. If the user wants a forced update, they run `cd ~/code/dev-stack && git pull` manually.

## Verification

After the commit, print the post-state:

```
team-mode enabled (<required|optional>)
  Project:         <path>
  Dev-stack remote: <url>
  Sync frequency:  once/hour on session start
  Committed files:
    .claude/settings.local.json
    .claude/hooks/session-start-sync.sh
    .claude/CLAUDE.md.team

Teammate onboarding: `git clone <remote> ~/code/dev-stack && ~/code/dev-stack/install.sh`
```

## Pairs with

- `kb-setup` — run after team-mode so the KB bootstraps for teammates too.
- `ship` — `team-mode` lives upstream of the deploy flow; each teammate can `/ship` with the same rules.
- `retro` — shared retro location if the team wants one aggregated weekly retro per repo.
