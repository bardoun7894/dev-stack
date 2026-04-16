# ts-runner — headless dev-stack team

Phase 2 of [dev-stack](../README.md). Runs the same 8-agent dev team (orchestrator + 7 specialists) outside the Claude Code CLI, for CI jobs, cron scripts, git hooks, or any non-interactive use.

The Markdown skills in `../skills/`, `../vendor/*/skills/`, and `../agents/` are the **single source of truth**. This runner reads those same files as system prompts — nothing is duplicated. Anything you edit in the Markdown skill flows automatically into both the Claude Code session and the headless runner.

## Status

Early MVP. Scope:

- [x] Project scaffold (`package.json`, `tsconfig.json`, types)
- [ ] Skill loader (reads Markdown skills + agents as strings)
- [ ] Orchestrator (NIU computation, model selection, parallel dispatch)
- [ ] Frontend worker (proof of shape)
- [ ] KB bridge (wraps `query.py`)
- [ ] Verification (runs project test suite)
- [ ] Remaining 6 workers
- [ ] Unit tests

## Install

```bash
cd ~/code/dev-stack/ts-runner
npm install
```

Set your API key:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

## Run

```bash
# Not yet implemented — coming in MVP
npm run dev-team "add a dark-mode toggle to the settings page"
```

## Architecture

```
ts-runner/
├── src/
│   ├── index.ts              # CLI entry (npm run dev-team "<task>")
│   ├── types.ts              # Packet, Role, ModelClass, Report shapes (Zod)
│   ├── skill-loader.ts       # Reads ../skills/<name>/SKILL.md, ../agents/<name>.md
│   ├── orchestrator.ts       # NIU + model selection + dispatch
│   ├── kb-bridge.ts          # Wraps query.py via child_process
│   ├── verify.ts             # Runs project test suite, parses pass/fail
│   └── workers/
│       ├── frontend.ts       # UI / CSS / React / Flutter
│       ├── backend.ts        # API / DB / server / migrations
│       ├── qa.ts             # Testing only
│       ├── debugger.ts       # Root-cause analysis
│       ├── designer.ts       # Design-system chain
│       ├── reviewer.ts       # Spec compliance + code quality
│       └── planner.ts        # Spec → tasks.md
└── test/
    └── *.test.ts             # vitest unit tests
```

## Why this exists alongside the Markdown skills

- **Claude Code skills** are Markdown — the CLI loads them as part of the interactive session. Great for humans driving the team.
- **ts-runner** is TypeScript — a program you can invoke from anywhere. Same team, same roles, same KB, no CLI required.

Both paths read the same Markdown files, so there is exactly one definition of what each role does.

## Not in scope

- **Multi-provider routing (Gemini / Codex / OpenAI).** Claude-only. Use `~/.local/bin/kb-capture` to ingest transcripts from other tools into the KB after the fact.
- **Replacing Claude Code.** The interactive CLI experience stays. ts-runner is an additional surface, not a replacement.
