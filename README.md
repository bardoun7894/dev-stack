# dev-stack

A complete one-company dev team for Claude Code, packaged as a single repo.

Bundles three skill collections plus a unified workflow skill, an adversarial
planner, a knowledge-base reminder hook, and an idempotent installer.

## What's inside

```
dev-stack/
├── skills/                          first-party
│   ├── kb-dev/                      unified end-to-end pipeline
│   └── grill-me/                    standalone adversarial planner
├── hooks/
│   └── user-prompt-kb-check.sh      injects KB reminders + auto-bootstrap
├── agents/                          (reserved for orchestrator/worker defs)
├── vendor/                          git submodules (read-only mirrors)
│   ├── kb-skill/                    bardoun7894/kb-skill   (8 kb-* skills)
│   └── superpowers/                 obra/superpowers       (14 workflow skills)
├── install.sh                       symlinks everything into ~/.claude/
├── CLAUDE.md.snippet                paste into ~/.claude/CLAUDE.md
└── README.md
```

## The 38-skill suite

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
| First-party    | dev-stack      | **kb-dev** (unified entry point), **grill-me** (standalone adversarial planner), **design-check** (conformance scanner), **design-md** (brand design system adopter) |

Total: **4 first-party + 8 kb-skill + 14 superpowers + 12 vendor-local = 38 skills.**

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
