# dev-stack

A complete one-company dev team for Claude Code, packaged as a single repo.

Bundles three skill collections plus a unified workflow skill, an adversarial
planner, a knowledge-base reminder hook, and an idempotent installer.

## What's inside

```
dev-stack/
├── skills/                          first-party (5 skills)
│   ├── kb-dev/                      unified end-to-end pipeline (the hub)
│   ├── grill-me/                    standalone adversarial planner
│   ├── design-check/                read-only design conformance scanner
│   ├── design-md/                   brand design system adopter
│   └── caveman/                     standalone output-style modifier (terse mode)
├── agents/                          8 registered Claude Code subagents
│   ├── orchestrator.md              opus — decompose / dispatch / aggregate
│   ├── planner.md                   sonnet — spec → role-tagged tasks.md
│   ├── frontend-engineer.md         sonnet — UI / CSS / React / Flutter
│   ├── backend-engineer.md          sonnet — API / DB / server / migrations
│   ├── qa-engineer.md               sonnet — testing & verification
│   ├── debugger.md                  sonnet→opus — root-cause analysis
│   ├── designer.md                  sonnet — full design workflow chain
│   └── reviewer.md                  sonnet — spec compliance + code quality
├── hooks/
│   └── user-prompt-kb-check.sh      injects KB reminders + auto-bootstrap
├── vendor/                          git submodules (read-only mirrors)
│   ├── kb-skill/                    bardoun7894/kb-skill   (8 kb-* skills)
│   └── superpowers/                 obra/superpowers       (14 workflow skills)
├── install.sh                       symlinks skills/ + agents/ + hooks/ + bin/
├── CLAUDE.md.snippet                paste into ~/.claude/CLAUDE.md
└── README.md
```

## How the framework works (skills + agents + orchestrator)

You (the parent Claude session) are the **controller of all skills**. When the user says "build X" / "implement Y" / "fix Z":

1. **Phase 0** — `kb-query` for prior art (mandatory)
2. **Compute NIU** (Number of Independent Units) from the request
3. **If NIU ≥ 2** — fan out by spawning role-specialist agents in parallel via the `Agent` tool. Each worker loads its own skill set and runs in its own context window
4. **If NIU = 1** — solo mode, do the work in the current session
5. **Aggregate worker reports**, run verification, review, finish, and capture knowledge

The **orchestrator** decides:
- Which agent type each work packet maps to (frontend / backend / qa / debugger / designer / reviewer / planner)
- Which model each worker runs on (haiku for trivial / sonnet for normal / opus for hard)
- How to batch packets if NIU > 4

If the parent session is Opus, **you ARE the orchestrator** — no need to spawn a separate Opus subagent. If the parent is Sonnet or Haiku, spawn the dedicated `orchestrator` subagent first.

## The 39-skill suite

| Layer          | Source         | Skills                                                                                                         |
|----------------|----------------|----------------------------------------------------------------------------------------------------------------|
| Knowledge base | kb-skill       | kb-setup, kb-query, kb-spec, kb-compile, kb-lint, kb-ingest, kb-docs-sync, kb-publish                          |
| Workflow       | superpowers    | brainstorming, writing-plans, executing-plans, dispatching-parallel-agents, subagent-driven-development        |
| Quality        | superpowers    | test-driven-development, verification-before-completion, systematic-debugging                                  |
| Review         | superpowers    | requesting-code-review, receiving-code-review, finishing-a-development-branch                                  |
| Branching      | superpowers    | using-git-worktrees                                                                                            |
| Meta           | superpowers    | writing-skills, using-superpowers                                                                              |
| Frontend / UI  | (vendored)     | adapt, animate, audit, clarify, harden, normalize, optimize, polish, quieter, frontend-design, vercel-react-best-practices |
| Orchestration  | (vendored)     | tech-company                                                                                                   |
| First-party    | dev-stack      | **kb-dev** (unified entry point), **grill-me** (standalone adversarial planner), **design-check** (conformance scanner), **design-md** (brand design system adopter), **caveman** (standalone output-style modifier — terse mode that respects kb-* citation rules) |

Total: **5 first-party + 8 kb-skill + 14 superpowers + 12 vendor-local = 39 skills.**

See [`docs/CONNECTIONS.md`](docs/CONNECTIONS.md) for the canonical skill-to-skill edge list and [`docs/RELATIONS.md`](docs/RELATIONS.md) for the human-readable map.

## Install

```bash
git clone --recursive https://github.com/<you>/dev-stack ~/code/dev-stack
cd ~/code/dev-stack
./install.sh
```

If you forgot `--recursive`:

```bash
git submodule update --init --recursive
```

Then add the hook block printed by `install.sh` to `~/.claude/settings.json`,
and append `CLAUDE.md.snippet` to `~/.claude/CLAUDE.md`.

## Update

```bash
cd ~/code/dev-stack
git pull
git submodule update --remote --merge
./install.sh   # idempotent, picks up any new vendored skills
```

## How it works

The unified entry point is **`/kb-dev`** — read `skills/kb-dev/SKILL.md` for
the full 12-phase pipeline and the solo-vs-fan-out decision rules.

The `user-prompt-kb-check.sh` hook fires on every user prompt:

1. Walks up from cwd to find `.git/` or `.claude/` (never crosses `$HOME`).
2. If no marker is found but cwd is under `$HOME`, runs `git init` to create one.
3. If `ai-knowledge-base/scripts/query.py` is missing → injects a "run /kb-setup" instruction.
4. If `.specify/templates/spec-template.md` is missing → injects a "run /kb-spec init" instruction.
5. Always appends the standing-rule reminder for `/kb-query` and `/kb-spec`.

## License

First-party files (`skills/kb-dev`, `skills/grill-me`, `hooks/`, `install.sh`):
choose your own license.

Vendored submodules retain their original licenses — see each `vendor/<repo>/LICENSE`.
