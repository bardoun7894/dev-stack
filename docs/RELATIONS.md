# dev-stack — skill relations map

This is the reference document for how all 40 skills in dev-stack connect to each other.
The canonical version lives inside `skills/kb-dev/SKILL.md`, and the per-edge list lives in
`docs/CONNECTIONS.md`. This file is the human-readable extract for humans who want the map
without scrolling through a SKILL.

## The hub-and-spoke model

`kb-dev` is the hub. Every other skill is reachable through one of its phases or as
an explicit standalone branch. Nothing is orphaned. Nothing duplicates.

```
                   ┌────────────────────────────────┐
                   │    kb-dev — unified pipeline   │
                   │       (12 phases, 1 hub)       │
                   └──┬─────────────────────────────┘
                      │
        ┌─────────────┼─────────────┬───────────────┬───────────────┐
        │             │             │               │               │
        ▼             ▼             ▼               ▼               ▼
    KB layer    spec layer    workflow layer   review layer    capture layer
        │             │             │               │               │
   ┌────┴───┐    ┌────┴────┐   ┌────┴───┐    ┌─────┴────┐    ┌─────┴─────┐
   │kb-query│    │kb-spec  │   │brain-  │    │requesting│    │kb-spec    │
   │kb-setup│    │  pre    │   │storming│    │-code-rev │    │  post     │
   │kb-ingest│   │  plan   │   │writing-│    │receiving-│    │kb-docs-   │
   │kb-lint │    │  tasks  │   │plans   │    │code-rev  │    │  sync     │
   │kb-publish   │  imple- │   │execut- │    │finishing-│    │kb-compile │
   │kb-docs-sync │  ment   │   │ing-    │    │a-dev-    │    │kb-lint    │
   │kb-compile   │  post   │   │plans   │    │branch    │    └───────────┘
   └────────┘    └─────────┘   │TDD     │    │using-git-│
                               │debug   │    │worktrees │
                               │verify  │    └──────────┘
                               │dispat- │
                               │ching   │
                               │subagent│
                               └────────┘
```

## The 12-phase pipeline (with auto-continue)

| #   | Phase                       | Sub-skills                                                            | Auto-continues?                       |
|-----|-----------------------------|-----------------------------------------------------------------------|---------------------------------------|
| 0   | Ground in prior art         | `/kb-query`                                                           | yes → 1                               |
| 1   | Brainstorm                  | `brainstorming`                                                       | yes → 2                               |
| 2   | Pre-spec KB research        | `/kb-spec pre` → `/speckit.specify` → `spec.md`                       | yes → 3                               |
| 2c  | System design (hard stop)   | `system-design` → `system-design.md` (fusion /opinion once)           | no: owner approves D/Q codes → 3      |
| 3   | Architectural plan          | `/kb-spec plan` → `/speckit.plan` → `writing-plans` → `plan.md`       | yes → 4                               |
| 4   | Task breakdown              | `/kb-spec tasks` → `/speckit.tasks` → `tasks.md`                      | yes → 5 (decision: solo vs fan-out)   |
| 5a  | Implement (solo)            | `executing-plans` in current session                                  | yes → 6                               |
| 5b  | Implement (fan-out)         | `dispatching-parallel-agents` + N × `subagent-driven-development`     | yes → 6 (per worker)                  |
| 6   | Test-first discipline       | `test-driven-development` inside each worker                          | yes → 7 if fail, → 8 if green         |
| 7   | Debug (only on failure)     | `systematic-debugging`                                                | yes → 6 (re-run tests)                |
| 8   | Verify before claiming done | `verification-before-completion`                                      | yes → 9                               |
| 9   | Request review              | `requesting-code-review`                                              | yes → 10                              |
| 10  | Apply review feedback       | `receiving-code-review`                                               | yes → 11                              |
| 11  | Finish branch               | `finishing-a-development-branch` + optional `using-git-worktrees`     | yes → 12 (PAUSE before merge to main) |
| 12  | Capture knowledge           | `/kb-spec post` → `/kb-docs-sync` → `/kb-compile` → `/kb-lint`        | end of pipeline                       |

## Auto-routing inside Phase 5 (UI/frontend tasks)

When a worker hits a UI task during Phase 5, the worker auto-routes to the right
specialist skill instead of writing CSS by hand:

| Task description contains…                                            | Auto-route to                |
|-----------------------------------------------------------------------|------------------------------|
| "build", "create", "design" + page/component/landing                  | `frontend-design`            |
| "responsive", "mobile", "breakpoint", "viewport"                      | `adapt`                      |
| "animate", "transition", "motion", "hover", "micro-interaction"       | `animate`                    |
| "polish", "alignment", "spacing", "looks off"                         | `polish`                     |
| "consistent", "design system", "tokens", "drift"                      | `normalize`                  |
| "harden", "edge case", "i18n", "overflow", "production-ready"         | `harden`                     |
| "slow", "laggy", "janky", "bundle size", "perf"                       | `optimize`                   |
| "a11y", "accessibility", "audit", "lighthouse"                        | `audit`                      |
| "confusing copy", "label", "error message", "microcopy"               | `clarify`                    |
| "too bold", "too loud", "calmer"                                      | `quieter`                    |
| React / Next.js component or perf work                                | `vercel-react-best-practices`|

These rules fire in both solo mode (Phase 5a) and fan-out mode (Phase 5b).

## Standalone branches (never auto-fire)

Powerful tools that the user must explicitly invoke. They are deliberately walled
off so they don't surprise the user mid-pipeline:

| Skill                | Trigger phrases                                          |
|----------------------|----------------------------------------------------------|
| `grill-me`           | "grill me", "stress-test this", "poke holes"             |
| `tech-company`       | "act as a tech company", "delegate to engineers"         |
| `design-check`       | "check the design", "is our theme respected"             |
| `design-md`          | "use the Linear aesthetic", "apply the Stripe design"    |
| `caveman`            | "caveman lite/full/ultra", "talk like caveman", "terse mode", "compress output" |
| `kb-ingest`          | "ingest these docs"                                      |
| `kb-publish`         | "publish KB to NotebookLM"                               |
| `kb-lint`            | "audit the KB"                                           |
| `writing-skills`     | "create a new skill"                                     |

## Design workflow chain

When the user is working on theme consistency, the preferred chain is:

```
design-md <brand>  →  design-check  →  normalize  →  polish  →  audit  →  finishing-a-development-branch
   (optional)          (read-only)     (fixes)      (pixels)   (a11y/perf)       (ship)
```

`design-check` auto-offers to invoke `/normalize` at the end of its scan. `/polish` closes
with `/audit` for the final quality pass before branch finishing.

## The two entry points

| User says…                                          | Entry point     | Path                                              |
|-----------------------------------------------------|-----------------|---------------------------------------------------|
| "build X", "implement Y", "ship Z", "fix bug A"     | `kb-dev`        | full 12-phase pipeline                            |
| "spec out X", "write a spec for Y"                  | `kb-spec`       | phases 0, 2, 3, 4 only — no implementation       |
| "what did we decide about X"                        | `kb-query`      | single-shot, returns cited [[wikilinks]]          |
| "polish the buttons" / "make it responsive"         | UI specialist   | direct to the matching vendor/local skill         |
| "grill me on this plan"                             | `grill-me`      | standalone, no pipeline                           |
| "act as a tech company"                             | `tech-company`  | standalone persona orchestrator                   |

## What the hook does

The `UserPromptSubmit` hook at `~/.claude/hooks/user-prompt-kb-check.sh`:

1. Walks up from cwd to find `.git/` or `.claude/` (never crosses `$HOME`).
2. Auto-`git init`s if cwd is under `$HOME` and has no marker.
3. Always injects "BOOTSTRAP REQUIRED: run /kb-setup" if `ai-knowledge-base/scripts/query.py` is missing.
4. Always injects "BOOTSTRAP REQUIRED: run /kb-spec init" if `.specify/templates/spec-template.md` is missing.
5. Smart-injects the standing-rule reminder ONLY when the prompt contains engineering vocabulary (saves ~150 tokens per trivial turn).

## Agent layer (8 registered subagents)

Skills handle "what to do". Agents handle "who does it in parallel". The 8 registered Claude Code subagents in `~/.claude/agents/` are:

| Agent              | Default model | Specialty                                   |
|--------------------|---------------|---------------------------------------------|
| `orchestrator`     | opus          | Decompose / dispatch / aggregate            |
| `planner`          | sonnet        | Spec → role-tagged tasks.md                 |
| `frontend-engineer`| sonnet        | UI / CSS / React / Flutter                  |
| `backend-engineer` | sonnet        | API / DB / server / migrations              |
| `qa-engineer`      | sonnet        | Testing & verification                      |
| `debugger`         | sonnet→opus   | Root-cause analysis                         |
| `designer`         | sonnet        | Full design workflow chain                  |
| `reviewer`         | sonnet        | Spec compliance + code quality              |

The orchestrator picks the model per worker based on packet complexity:
- **trivial** (lookups) → `haiku`
- **simple/medium** (most work) → `sonnet`
- **hard** (architectural reasoning, hairy debugging) → `opus`

**Fan-out fires at NIU ≥ 2** (Number of Independent Units) — the previous threshold of 4 was too conservative and is the reason fan-out almost never fired automatically.

If the parent session is Opus, the parent IS the orchestrator (no need to spawn a separate Opus subagent). If parent is Sonnet/Haiku, spawn the orchestrator as a separate subagent.

## Token cost summary

| Mechanism                          | Cost                                  |
|------------------------------------|---------------------------------------|
| 39 skill descriptions at session start | ~12 kB of metadata (one-time)     |
| 8 agent definitions in ~/.claude/agents/ | ~8 kB total — only loaded on Agent spawn, not in every prompt |
| Smart hook on engineering prompt   | ~150 tokens                           |
| Smart hook on trivial prompt       | 0 tokens                              |
| `kb-query` cited answer            | ~200-500 tokens (vs. 5k+ for raw file reads) |
| Fan-out worker (Phase 5b)          | each worker = its own 200k context, main thread sees only the diff summary (~200-1000 tokens per worker) |
| Total typical-session savings      | ~5k tokens vs. linear single-agent flow |
