# RETIRED 2026-10-27: fan-out, packets, role roster. Replaced by WORK SPLIT (one implementer per spec). Kept for history; do not follow.

## Decision: solo vs fan-out (NIU-based, threshold = 2)

The fan-out gate is the **Number of Independent Units** (NIU) in the work — *not* the number of tasks in tasks.md. NIU counts work that touches different files, different subsystems, with no sequential coupling.

| NIU | Mode | What you do |
|----|------|-------------|
| **1** | **Solo** (phase 5a) | One `executing-plans` run in current session. No orchestration. |
| **2-4** | **Fan-out** (phase 5b) | Spawn one specialist agent per unit, all in parallel, in a single message. |
| **5-8** | **Fan-out with batching** | Group into 4 packets, distribute units across them. Cap at 4 parallel workers. |
| **9+** | **Stop and escalate** | Tell the user "this is too big, suggest narrowing scope". |

**Fan-out fires at NIU ≥ 2.** Not 4. The previous threshold was wrong and is the reason fan-out almost never fired automatically.

### How to count NIU when there's no tasks.md

The user almost never runs `/speckit.tasks` first. So you derive NIU yourself:

1. Read the user's request and any files they pointed at
2. Identify the subsystems the work touches (UI, API, DB, tests, docs, deployment)
3. Identify the file boundaries — which files share state, which don't
4. NIU = number of subsystem × file-boundary intersections that have no sequential coupling

Examples:
- "Add a settings page" → NIU = 2 (frontend + backend, parallel)
- "Fix this bug in api_service.dart" → NIU = 1 (single file, single root cause)
- "Refactor the booking flow across the Flutter client and Laravel API" → NIU = 3-4 (frontend + backend + tests + maybe migrations, parallel)
- "Update the README" → NIU = 1 (single file, no test surface)

**If NIU ≥ 2, you fan-out. No "should I ask first" — you fan-out.** Asking the user "solo or fan-out?" wastes a turn for borderline cases. The only borderline that needs asking is NIU = 1 vs 2 when the work is genuinely small.

## Who is the controller?

**You (the current Claude session) are the controller of all skills and the god of dispatch.** The orchestrator is a *role*, and the main session always plays it: decompose in this session, whatever your model. All 11 dev-stack agents (`orchestrator`, `planner`, the specialists, ...) are parked in `~/.claude/agents-parked`, so `Agent(subagent_type: "orchestrator" | "<specialist>")` does not resolve. Dispatch workers like this:

| Need | How |
|------|-----|
| One worker | `jdelegate --cwd <repo> --name <label> [--role <specialist>] "<brief>"`. Jev routes the model and, when omitted, picks the role, skills and MCP servers. |
| Independent units (NIU ≥ 2) | One `jdelegate` call per unit, each started in the background in the same turn; collect the results when they finish. |
| A parked agent through the `Agent` tool | Only after `bash scripts/park-skills.sh unpark-agent <name>`; park it again when done. |

When in doubt about the worker's model, let `jdelegate` route it.

### Model selection per worker

When you (or the orchestrator) spawn workers, pick the model based on packet complexity:

| Class | Model | Examples |
|-------|-------|----------|
| **trivial** | `haiku` | "Does X exist in file Y?", "What's the value of Z?", single-line factual lookups |
| **simple** | `sonnet` | Add a button, fix a typo'd label, add one test case (< 100 LOC, 1-2 files) |
| **medium** | `sonnet` | New API endpoint with tests, refactor a service class, fix a non-trivial bug (100-500 LOC, 3-10 files) |
| **hard** | `opus` | Migration between auth schemes, race-condition debugging without a clear hypothesis, novel architecture (500+ LOC, 10+ files, cross-cutting) |

Default: `sonnet`. Bump to `haiku` for trivial lookups (cheap), bump to `opus` only when Sonnet would get stuck (expensive but justified).

The full classifier and per-role defaults live in `~/code/dev-stack/agents/orchestrator.md` — read that file's "complexity rubric" section if unsure.

## Mandatory sequencing rules

1. **Never skip phase 0** — always run `/kb-query` first, even if you think you know the answer. The KB has history you will not remember.
2. **Never skip phase 2a** — Research (KB prior art + library docs at repo versions + 2-3 competitor references with URLs + risks) must land in `specs/NNN/research.md` before any Phase 3 design decision. Dispatch `jdelegate --no-auto-mcp --no-auto-skill --no-auto-role --role researcher`; one read-only pass, output is `specs/NNN/research.md`.
3. **Never skip phase 8** — `verification-before-completion` runs the full test suite and the user's definition of done. Saying "done" without it is the most common failure mode.
   - Web change with WebMCP tools: unit test with the modelContext mock + live check in Chrome with the testing flag.
4. **Phase 9 review is mandatory** — `requesting-code-review` runs on every change that touches code. The only exemption is a diff that contains zero code/config changes (docs-only). One reviewer pass + one `receiving-code-review` fix round; only **P0** and **P1** findings block. P2/P3 are informational and do not gate the branch. Treat phase 9 as a gate: no `finishing-a-development-branch` (phase 11) before review findings are triaged.
5. **Capture knowledge in phase 12** — without `/kb-spec post` + `/kb-compile`, the next feature will not benefit from what you just learned.
6. **Fan-out guardrail** — never spawn more than 4 parallel workers without user confirmation. Cost and debugging difficulty grow non-linearly past that.
7. **Fan-out tripwire** — if NIU ≥ 2, you MUST start parallel workers (`jdelegate` calls in the background) BEFORE doing any edits yourself. Doing the work serially in the parent session when fan-out is appropriate is the second most common failure mode.

## The team roster (registered subagents)

When you fan out, you hand one of these specialist roles to a worker with `jdelegate --role <name> ...` (the role definition is inlined into the worker's prompt). The definitions are installed by `dev-stack/install.sh` and currently parked in `~/.claude/agents-parked`; `jdelegate` finds them there. Use the `Agent` tool with one of them only after `bash scripts/park-skills.sh unpark-agent <name>`.

| Agent name           | Default model | Specialty                                      | Loads on startup                                                            |
|----------------------|---------------|------------------------------------------------|-----------------------------------------------------------------------------|
| `orchestrator`       | opus          | Decompose + dispatch + aggregate               | Reads tasks.md, spawns workers in parallel                                  |
| `planner`            | sonnet        | Spec → role-tagged tasks.md                    | Substitute for `/speckit.tasks` when none exists                            |
| `frontend-engineer`  | sonnet        | UI / CSS / React / Flutter                     | TDD, frontend-design, polish, animate, adapt, normalize, harden, optimize, audit, clarify, quieter, vercel-react-best-practices |
| `backend-engineer`   | sonnet        | API / DB / server / migrations                 | TDD, verification-before-completion, systematic-debugging                   |
| `qa-engineer`        | sonnet        | Test writing, fixing, regression sweeps        | TDD, verification-before-completion                                         |
| `debugger`           | sonnet→opus   | Root-cause analysis, regression test authoring | systematic-debugging, TDD, verification-before-completion                   |
| `designer`           | sonnet        | Full design workflow chain in one context      | design-md, design-check, normalize, polish, audit, TDD                      |
| `reviewer`           | sonnet        | Spec compliance + code quality review          | requesting-code-review, receiving-code-review                               |
| `researcher`         | sonnet        | Read-only prior-art + library-docs + competitor scan → specs/NNN/research.md | (web access, no writes outside specs/NNN/research.md)        |

You may also spawn `general-purpose` subagents with `model: haiku` for trivial one-shot lookups (e.g. "does X exist in file Y?").

### Fast-path: no tasks.md needed

If the user says "build X" / "implement Y" / "fix Z" and there is no `specs/<feature>/` yet, you do **not** need to run `/speckit.specify` → `/speckit.plan` → `/speckit.tasks` first. The fast path is:

1. Phase 0 — `/kb-query` (mandatory)
2. **Compute NIU yourself** from the user's request and any files mentioned
3. If NIU ≥ 2 — produce the tasks.md substitute yourself (or `jdelegate --role planner`), then immediately dispatch specialists from its output, all in one turn
4. If NIU = 1 — solo mode, do the work in the parent session
5. Phases 6-12 run as normal after workers return

This skips Spec Kit entirely for small-to-medium features. Use the full Spec Kit pipeline only for features big enough to deserve a `spec.md` artifact for posterity.

## Model assignment

- **Opus** → the main session as orchestrator (when it runs on Opus), decomposing tasks.md into work packets; workers get whatever `jdelegate` routes.
- **Sonnet** → the default for all worker agents, implementation, debugging, review.
- **Haiku** → cheap one-shot lookups the orchestrator needs (file existence, single-file read summaries, "does this symbol exist"). Spawn via `Agent(model: "haiku", ...)`.

