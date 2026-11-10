---
name: factory-issues
description: See a project's specs and what the software factory is doing with its GitHub issues, and file factory issues (the owner's request, or on your own when a session finds follow-up work). Labeled issues are built by the factory on MyContabo into a PR plus a Telegram preview card; the owner merges. Use on "show the specs", "what specs does X have", "what is the factory doing", "factory issues", "create an issue", "file this for the factory", "let the factory do it", "شوف السبيكس", "دير issue", and on your own at the end of work that leaves a bug, a follow-up or an unfinished task outside your scope in a project with intake on.
allowed-tools: Bash Read Write
---

# factory-issues: specs in, issues out

Everything runs on MyContabo (`ssh MyContabo ...` from the Mac or CachyOS; drop the ssh when already there). The repos,
`projects.json` and the factory live there. Never print secrets; never put client personal data, tokens or `.env`
values in an issue (issues are visible to anyone with repo access).

## See the specs

```bash
ssh MyContabo python3 ~/.claude/skills/factory-issues/scripts/specs.py              # projects, spec counts, intake on/off
ssh MyContabo python3 ~/.claude/skills/factory-issues/scripts/specs.py mediatgb     # one row per spec: tasks done/total, merged
ssh MyContabo python3 ~/.claude/skills/factory-issues/scripts/specs.py mediatgb 083 # one spec: title, stamp, open tasks
```

It reads a git ref, never the working tree: `preview_watch_branch` when the project has one (crmai: `001-crm-mvp`),
else `<remote>/<main>` after a fetch. `--ref BRANCH` reads another ref. Show the table, then answer the question; do not
paste whole spec files unless asked.

## See what the factory is doing

```bash
ssh MyContabo factoryctl intake-status --project mediatgb     # each issue: stage, history, branch, PR, preview
ssh MyContabo factoryctl intake-status --json                 # all projects, machine-readable
```

Stages: `intake` (being read) → `needs-info` (questions on the issue) | `rejected` | `building` → `pr-open` (PR plus
preview card) | `needs-human` (failed; `factoryctl feedback <project> <n>` with text on stdin rebuilds with your note,
`factoryctl reject <project> <n>` drops it). `proposed` = filed but waiting for the owner to add the `factory` label.
The same feed is the Issues panel in GodHome (https://www.mbardouni.dev/godhome, Factory tab).

## File an issue

1. Check the project has intake on (`specs.py` shows `intake=on`). Off: say so and stop; do not file.
2. Write the body in the intake's ticket shape, so it is accepted instead of answered with questions:

   ```markdown
   ## Goal
   One or two sentences: what changes for the user and why.
   ## Where
   Files or screens, if known.
   ## Done when
   - **F1 <flow name>:** who does what, and what they see.
   ## Do not touch
   Areas that must not change.
   ## Size
   small | normal
   ```
   One issue = one change a reviewer can check in one sitting. Split bigger work.
3. File it (the body goes as a file, never inline in a shell string):

   ```bash
   scp body.md MyContabo:/tmp/issue-body.md
   ssh MyContabo factoryctl issue-new mediatgb --source owner --title "Login page: announce errors" --body-file /tmp/issue-body.md
   ```
   Output: `created <url>` (building), `proposed <url>` (waits for the owner), or `duplicate <url>` (already filed).
4. Tell the owner the URL in one line.

`--source`:
- `owner`: the owner asked for this issue. Builds; never capped.
- `session`: you decided to file it (see below). Builds, at most 3 AI issues per project per day; more become `proposed`.
- `review`, `spec`, `tokyo`: used by the factory's own scanners and Tokyo, not by sessions.

## Filing on your own (source `session`)

At the end of work, when you found something real that is outside your task's scope and you did not fix it, in a
project with intake on: a reproducible bug, a missing test for a risky path, a follow-up the spec names but did not
build. File one issue per item with `--source session`, then list the URLs in your final report.
Do not file: style opinions, anything you could fix within scope, duplicates of open work, secrets or client data,
work on projects with intake off. `duplicate` is a normal answer, not an error.

## Checks

- `bash ~/code/dev-stack/tests/test_factory_specs.sh` tests `specs.py`.
- `issue-new`, `intake-status`, `feedback`, `reject` are tested in software-factory (specs 012, 013).
