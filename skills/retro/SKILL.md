---
name: retro
description: Two modes. (1) `/retro session [last N | <id>]` — audit real Claude Code session transcripts (default: current session) for hidden waste and risk: navigation, missing/unwired automated checks, coding standards, bloated or no-op steering files, tool economy, missing information, irreversible actions taken without asking; presents ranked fixes for the human to pick, never auto-applies (after Matt Pocock skills v1.3 `retro`, MIT). Triggers "retro this session", "session retro", "what went wrong in that session", "audit my last sessions", "/retro session". (2) Weekly engineering retrospective — reads last 7 days of KB daily logs, compiled concepts, git activity, shipped PRs, open incidents, writes `retros/YYYY-WW.md`. Triggers "weekly retro", "run the retro", end-of-week. Neither mode auto-fires.
allowed-tools: Bash Read Write Grep Glob
---

# retro — session audit + weekly retrospective

Pick the mode from the request: a session, a transcript, "what went wrong" → **Session mode**.
A week, a sprint, "weekly" → **Weekly mode** (further below).

## Session mode — audit real agent sessions

Agents rarely complain. They push through broken tools, missing checks and lost context and still
finish, so the waste stays hidden. Session mode reads what actually happened and proposes changes to
the agent's **environment** (repo, checks, steering files, tools) so the next run is cheaper and safer.

### Steps

1. **Digest, never raw JSONL.** Transcripts are 100 KB–10 MB. Run the zero-AI digest and read only its output:
   ```bash
   python3 ~/code/dev-stack/skills/retro/scripts/session-digest.py            # current/newest session
   python3 ~/code/dev-stack/skills/retro/scripts/session-digest.py last 5     # sample of recent sessions
   python3 ~/code/dev-stack/skills/retro/scripts/session-digest.py <id-prefix>
   ```
   It prints tokens, compactions, tool-call counts, the heaviest tool results, repeated calls, tool
   errors, hook blocks and the user's messages. Open a specific transcript slice (`grep -n` on the
   jsonl, then `sed -n`) only to confirm one finding. Pi sessions: `~/.pi/agent/sessions/`.
2. **Read the repo's own guardrails first**: CLAUDE.md/AGENTS.md size, `package.json`/`composer.json`/
   `Makefile`/`pubspec.yaml` check scripts, `.github/workflows/`, pre-commit hooks, `CODING_STANDARDS.md`.
   A check that exists but nothing runs is the finding — not a new check.
3. **Look for candidates** in these categories:
   - **Irreversible actions**: did the agent push, deploy, release, delete, send a message, or touch
     prod/`~/.claude` without asking? Highest severity. Fix = a hook, a confirm step, or a memory rule.
   - **Navigation**: long searches to find one file or fact → a one-line navigation pointer in
     CLAUDE.md/AGENTS.md, or a docs file the pointer names.
   - **Automated checks**: a mistake a lint/type/test/CI step would have caught; or a repo with no
     guardrail at all (no pre-commit and no CI running lint/typecheck/test) — that alone is a finding.
   - **Coding standards**: mechanical violations get a deterministic check (lint rule, hook, CI job),
     not prose. Only judgement calls go to `CODING_STANDARDS.md` (read by the reviewer, not the implementer).
   - **Steering-file health**: global `~/.claude/CLAUDE.md`, project CLAUDE.md, memory index — instructions
     that should be checks or standards instead, and **no-ops** (lines that change nothing the agent does).
   - **Tool economy**: heavy results (large `cat`, unbounded `ps`/`grep`, full test logs), repeated calls,
     custom CLIs/MCPs that waste tokens, compactions that lost context → a better script, a flag, a skill.
   - **Information access**: what the agent needed but could not see (server logs, a service, a PATH entry).
   - **Rule/hook friction**: a hook blocked legitimate work (see `hook blocks` / `tool errors`). Hand these
     to the `self-tune` skill, which owns TOKEN BUDGET, `no-poll-guard.sh` and the gate kit.
4. **Present** findings ranked by severity, coded `F1, F2…`. Each: what happened (cite the digest line),
   the proposed environment change (exact file + the change), and its cost. Lead with the 1–3 worth doing.
5. **Stop.** The human picks what to apply. Never apply fixes in the same run, never loop retro on its
   own output — automated retro drifts into fixing false positives. Run it on a sample of sessions,
   especially ones that felt off.
6. If the user accepts findings and the project has `ai-knowledge-base/`, write them to
   `ai-knowledge-base/raw/retro-session-YYYY-MM-DD.md` for `/kb-ingest`.

### Where a fix belongs

| Change | Home |
|---|---|
| Pointer to where things live | CLAUDE.md / AGENTS.md (keep tiny — loads into every implementer) |
| Judgement-call rule | `CODING_STANDARDS.md` (reviewer reads it, implementer does not) |
| Mechanical rule | lint rule, pre-commit hook, CI job |
| Repeated multi-step procedure | a skill (its description is what loads, so write it well) |
| Fact about this machine/user | memory file |

## Weekly mode — engineering retrospective


A structured Friday-afternoon reflection that turns a week of scattered work into a single markdown page. Read-only against the KB; writes one new `retros/YYYY-WW.md`.

## When it fires

- User says "run the retro", "weekly retro", "/retro"
- End of week (default: Friday or Sunday; user can override)
- After `/ship` on a significant feature, as a "zoom out" moment

Never auto-fires mid-week — retros need a full week of data to be useful.

## Inputs

1. **KB daily logs** — `ai-knowledge-base/daily/YYYY-MM-DD.md` for the last 7 days
2. **Compiled concepts** — `ai-knowledge-base/knowledge/concepts/*.md` touched in the last 7 days (by file mtime)
3. **Git activity** — commits on all branches in the last 7 days:
   ```bash
   git log --all --since="7 days ago" --pretty="%ad %h %s" --date=short --no-merges
   ```
4. **Shipped PRs** — merged in the last 7 days:
   ```bash
   gh pr list --state merged --search "merged:>$(date -v -7d +%Y-%m-%d)" --json number,title,mergedAt,url
   ```
5. **Open incidents / bugs** — P0/P1 issues still open:
   ```bash
   gh issue list --label "P0,P1,incident" --state open --json number,title,url
   ```

If any input is unavailable (no KB, no git, no `gh`), proceed with what's there and note the gap.

## Output template

Write to `retros/YYYY-WW.md` at the project root (create `retros/` if missing). Week number = ISO week (`date +%V`).

```markdown
# Retro: week YYYY-WW (<date range>)

**Generated:** <ISO>
**Shipped:** N PRs · <line count> logical lines
**Open P0/P1:** N
**KB growth:** +N concepts · +N sources

## Wins
- <PR title #N> — <one-sentence impact>
- ...

## Blockers / drag
- <thing that slowed us> — <cause>
- ...

## Themes
- <pattern noticed across the week — e.g. "most incidents came from X">
- ...

## Decisions made
- <decision + rationale, linked to [[wikilinks]] in the KB>
- ...

## Next week's bets (3 max)
1. <concrete, time-boxed goal>
2. ...

## Signals to watch
- <metric or threshold to monitor>

## KB citations
- [[concepts/foo]] · [[sources/bar]]
```

## Rules

- **Never invent wins.** If the week had no shipped PRs, say so.
- **Themes must have ≥ 2 data points.** A single incident is a finding, not a theme.
- **Max 3 "next week's bets".** More than 3 = none will happen.
- **Decisions must cite the KB** — every decision links to at least one `[[wikilink]]`.
- **Skip the file entirely if < 10 commits that week** — a retro on 2 commits is noise. Tell the user instead.

## Cost

One `/kb-query` call to collate concepts, one for decisions. ~$0.10-$0.20. LLM model picked by `pick_model("query-deep")` → sonnet.

## Pairs with

- `kb-compile` — run this first if daily logs are uncompiled (retros need compiled concepts).
- `ship` — last-week's deploys are the main source of "wins".
- `kb-publish` — mirror the retro to NotebookLM so it becomes queryable later.
- `office-hours` — often the next-week's bets become the starting point for office-hours on Monday.
