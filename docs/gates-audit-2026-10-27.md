# Gates audit: hard rules vs enforcement (2026-10-27)

Scope: rules in `~/.claude/CLAUDE.md` (after the WORK SPLIT rewrite) and `~/.claude/reference/*.md`. Report only; no hook was changed. Enforcement checked against `~/.claude/settings.json` hook wiring and `~/.claude/hooks/`, `~/.githooks`, `scripts/gate/`.

| # | Hard rule | Enforced by | Status | Proposal (prompt-only rules) |
|---|-----------|-------------|--------|------------------------------|
| G1 | Never poll background output; never read subagent transcripts | `hooks/no-poll-guard.sh` (PreToolUse Bash/Read) | Hook | none |
| G2 | Every `jdelegate` carries `--no-auto-role` or `--role NAME` | `no-poll-guard.sh` | Hook | none |
| G3 | One agent per branch; no commit/push on a held branch | `branch-lock-guard.sh` (PreToolUse Bash) + `~/.githooks` pre-commit/pre-push | Hook | none |
| G4 | No commits on main/master/production | `~/.githooks/pre-commit` | Hook | none |
| G5 | Heavy server commands go through `gate-run` | `hooks/gate-run-guard.sh` (PreToolUse Bash; copy in `~/.claude/hooks/`) blocks heavy commands on `ssh MyContabo` and on the server unless wrapped in `gate-run <project> ... --` | Hook | none |
| G6 | Full suites only in the gate queue | `hooks/gate-run-guard.sh` (same hook as G5; `scripts/gate/gaterun.sh` is the queue) | Hook | none |
| G7 | Orchestrator mode: no direct edits, no built-in Agent tool | `hooks/orch-block-edits.sh` (only when CLAUDE_ORCH=1) | Hook (partial) | Document that plain sessions are intentionally unguarded |
| G8 | Unbounded Read of files over 25 KB denied | `hooks/read-size-guard.sh` | Hook | none |
| G9 | No finishing with uncommitted work | `hooks/commit-guard.sh` (Stop, once) | Hook (soft) | none |
| G10 | No Co-Authored-By / "Generated with" in commits | None found | Prompt-only | `commit-msg` hook in `~/.githooks` rejecting those lines; deny pattern for `gh pr create --body` |
| G11 | Run `/kb-query` before edits; log task with `/kb-spec log` | `user-prompt-kb-check.sh` reminder + `hooks/kb-log-guard.sh` (Stop, warn only, once per session per repo; copy in `~/.claude/hooks/`) warns when a repo was edited or committed with no `specs/_session/<today>-tasks.md` and no `/kb-spec log` call | Hook (warn) | none |
| G12 | Mark done only in the spec (tasks.md box + SHA) | None | Prompt-only | Phase 11 gate script: fail if tasks.md has unchecked boxes at PR time |
| G13 | One review + one fix round per branch | `bin/jdelegate`: per repo+branch counter in `$CACHE/review-count.json`, refuses the 3rd `--role reviewer` run (exit 2); `JDELEGATE_REVIEW_FORCE=1` bypasses | Script | none |
| G14 | Review fixes go to the SAME implementer session (new) | None | Prompt-only | `jdelegate --resume <name>` convention; refuse a second worker `--name` on the same spec branch while the first is alive |
| G15 | Never split one spec into parallel workers (new) | `overlap.sh` catches shared files only | Prompt-only | extend `overlap.sh` to also fail when two live workers share a spec dir |
| G16 | Reviewer sees only spec + diff, Opus xhigh | `agents/reviewer.md` model pin | Config + code | `jdelegate --role reviewer` forces auto skill/role/MCP off, refuses `--skill`/`--mcp`/`--full` and briefs that cite a `*.jsonl`, the jdelegate cache dir or `--resume` (exit 2; `JDELEGATE_REVIEW_CONTEXT=1` overrides), and warns when the brief names no spec or no diff |
| G17 | Every spec has a "Done when" with user-flow matrix (new) | None | Prompt-only | add grep check to Phase 11 gate and to `/kb-spec tasks` template |
| G18 | Verifier resets DB/state between flows, non-prod only | `scripts/gate/verify-env-guard.sh` + `scripts/gate/prod-db-patterns.txt` + `scripts/gate/verifier-brief-template.md` | Script | none |
| G19 | Locked checks untouched by builder | `lock-checks` (deny rule + pre-commit + verify) | Script | none |
| G20 | Deploy only after "Deploy it?" yes | `tokyo-deploy` ask/yes flow; deploy by another path is not blocked | Partial | hooks/deploy-guard.sh (PreToolUse Bash, both machines) denies deploy commands without an approved TOKYO_OFFER; Tokyo must export TOKYO_OFFER into deploy runs |
| G21 | Server-first: website work on MyContabo | `hooks/server-first-warn.sh` (SessionStart, Darwin only; copy in `~/.claude/hooks/`) | Hook (warn) | none |
| G22 | New project = own folder + kb-setup + kb-spec init | `user-prompt-kb-check.sh` injects "run /kb-setup now" | Reminder only | none |
| G23 | Max 3 parallel workers | `bin/jdelegate`: refuses a new non-resume worker when 3 live records exist (reviewer, verify*, research* exempt); `JDELEGATE_MAX_LIVE` overrides | Script | none |
| G24 | Comms contract (banned phrases, codes) | `hooks/comms-guard.sh` + `hooks/comms-banned.txt` (Stop, warn only; copy in `~/.claude/hooks/`) | Hook (warn) | none |
| G25 | No completion claim without pasted output | `verification-before-completion` skill only | Prompt-only | leave as is; low-precision to detect |
| G26 | Jev first for labels/scores | `skills/jev`, no hook | Prompt-only | leave as is |

Rules marked "(new)" come from the 2026-10-27 WORK SPLIT rewrite. Highest value to automate first: G10, G12/G17 (one Phase 11 gate script), G14/G15.
