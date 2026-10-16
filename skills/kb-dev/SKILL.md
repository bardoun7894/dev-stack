---
name: kb-dev
description: Unified 12-phase dev pipeline. Chains kb-query → brainstorming → kb-spec → writing-plans → implement (solo or fan-out) → TDD → verify → review → finish → kb capture. Use for any non-trivial feature/build/ship request. Read SKILL.md for the phase table.
allowed-tools: Bash Read Write Edit Glob Grep Agent Skill
---

# kb-dev — the unified dev-team workflow

This skill is the **single entry point** for any non-trivial engineering task. It does not do the work itself. It orchestrates the other skills you already have installed:

| Phase                      | Sub-skill                                                                              | Model          |
|----------------------------|----------------------------------------------------------------------------------------|----------------|
| 0. Ground in prior art     | `/kb-query`                                                                            | (no agent)     |
| Jev down (402 / out of quota) | Nothing to change: `jev` and `jdelegate` fall back to local Laya (`laya-serve`, `engine: laya`, every `--min` gate fails closed); `jev-browse` and `jev-review` stay on Jev only and exit 3, so phase 8/9 use their normal LLM path. See `skills/jev/SKILL.md` "Local fallback: Laya" | auto |
| 1. Brainstorm options      | `brainstorming` (obra)                                                                 | inline         |
| 2. Pre-spec KB research    | `/kb-spec pre` → `/speckit.specify`                                                    | inline         |
| 2a. Research (mandatory)   | `jdelegate --no-auto-mcp --no-auto-skill --no-auto-role --role researcher` (one pass, read-only) → `specs/NNN/research.md` | Sonnet (read-only + web) |
| 3. Architectural plan      | `/kb-spec plan` → `/speckit.plan` → `writing-plans` (obra)                             | inline         |
| 4. Task breakdown          | `/kb-spec tasks` → `/speckit.tasks`                                                    | inline         |
| 4b. **Branch (MANDATORY)** | **`git checkout -b <NNN-short-name>` — branch must match the spec dir. Never implement on `main`.** | inline |
| 5a. Implement (solo)       | `executing-plans` (obra) in current session                                            | Sonnet         |
| 5b. Implement (fan-out)    | `dispatching-parallel-agents` + `subagent-driven-development` (obra)                   | Opus → Sonnet  |
| 6. Test-first discipline   | `test-driven-development` (obra) inside each worker                                    | Sonnet         |
| 6a. Approve + lock checks | list checks in plain words → wait for user OK → `lock-checks approve <tests>` → loops/workers call `lock-checks verify` after each round; a failing verify = round undone | inline |
| 7. Debug if something fails| `systematic-debugging` (obra)                                                          | Sonnet         |
| 8. Verify before claiming  | `verification-before-completion` (obra); UI change → web: `jev-browse --flows` first (Jev System 1 agent, see `skills/jev/references/e2e-browsing.md`); mobile (Expo/RN): `npx e2e run` (see Phase 8: e2e suites) | Sonnet |
| 9. Request review          | `jev-review diff` first (System 1 screen): its `route` picks the reviewer alone, plus `/codex`, or plus `/panel`; then `requesting-code-review` (obra) | Sonnet |
| 10. Apply review           | `receiving-code-review` (obra)                                                         | Sonnet         |
| 11. Finish branch          | `finishing-a-development-branch` (obra) — **always ends in a PR** — optional: `using-git-worktrees` | inline |
| 12. Capture knowledge      | `/kb-spec post` → `/kb-docs-sync` → `/kb-compile` → `/kb-lint`                         | inline         |

## Phase 4b: branch before you implement (non-negotiable)

**One spec = one branch = one PR.** The branch name must equal the spec directory name, because `kb-spec` resolves the active feature via `$SPECIFY_FEATURE` → current git branch `NNN-short-name` → *else* highest `NNN` under `specs/`. If the branch does not exist, that resolution silently falls through to the last case and every feature collapses onto whatever branch is checked out — in practice, `main`.

```bash
# specs/012-adw-quality-gates  →  branch 012-adw-quality-gates
git checkout -b "$(basename specs/012-adw-quality-gates)"
```

`/speckit.specify` already does this (`create-new-feature.sh` runs `git checkout -b` and exports `SPECIFY_FEATURE`). When a spec dir is created by hand or by `/kb-spec` without going through `/speckit.specify`, **you must create the branch yourself** before Phase 5.

Enforcement is mechanical, not advisory: `~/.githooks/pre-commit` (global `core.hooksPath`) refuses commits on `main`/`master`/`production`. Merges, rebases, cherry-picks and reverts are allowed, so PRs still land normally. If you genuinely need to bypass it:

```bash
ALLOW_MAIN_COMMIT=1 git commit ...          # once
git config devstack.allowMainCommit true    # this repo, permanently
```

Never reach for the override to route around a missing branch — create the branch instead.

## Phase 8: e2e suites

Phase 8 is the gate for UI changes. Run the suite that matches the app before saying the change works.

- Web: `jev-browse --flows e2e/flows.json` (see `skills/jev/references/e2e-browsing.md`).
- Mobile (Expo/RN; Flutter and native not yet verified for `e2e init`): TesterArmy `e2e`, `npx e2e run --target ios`.
- Evergreen suite: the full mobile flow set, run on every PR by `.eas/workflows/e2e-tests.yml`. Commit `.e2e/cache` so CI replays the verified `act` steps at L0 with no model call.
- Per-PR exploration run: the PR diff and description drive a run that tests the changed features, next to the evergreen suite. Its caching is not documented; assume it pays the model each time until measured.
- On a failure, read `.e2e/artifacts/**/screen.txt` before changing a locator.
- Agent steps: Jev decision executor; text model Haiku 5.5, Arabic screens included; GPT-6 Luna only to judge Arabic wording (see the jev reference).
- Per-PR results go to the PR as a comment via `@e2e-dev/github`.

## Phase 6a: lock the checks before building

The scorer must be untouchable by the builder, or a loop can pass by weakening the tests.

1. Write the checks before the code (Phase 6).
2. Run `lock-checks list <tests>` and show the user each check in plain words. Wait for an explicit OK.
3. `lock-checks approve <tests>` moves them to `tests/locked/` (override with `LOCKED_DIR`), adds an `Edit(...)` deny rule (covers all file-editing tools) to `.claude/settings.json`, commits (rolling everything back if the commit fails), records the approved tree hash in `$(git rev-parse --git-common-dir)/lock-checks/manifest`, and installs a git pre-commit hook in the common git dir (so linked worktrees are covered) that rejects any later commit touching a locked dir.
4. The builder may never edit the locked dir. Loops and workers run `lock-checks verify` after every round; `verify` compares the locked dir against the recorded tree, so committed (even `--no-verify`) and uncommitted tampering both exit 1, which means the round is undone.
5. Only a human runs `lock-checks unlock` (it refuses to overwrite an existing `tests/<sub>`) and commits the result with the human-only env bypass (see `lock-checks -h`). An agent that needs a check changed stops and asks.

## Phase 11 gate: prove the branch and the PR exist

Do not report a feature as finished on assertion. Run these and paste the output — evidence, not claims:

```bash
# 1. Not on a protected branch
BR=$(git rev-parse --abbrev-ref HEAD)
case "$BR" in main|master|production)
  echo "FAIL: still on $BR — the work was never branched"; exit 1 ;;
esac
echo "OK branch: $BR"

# 2. Branch matches the spec dir (one spec = one branch = one PR)
[ -d "specs/$BR" ] && echo "OK spec: specs/$BR" || echo "WARN: no specs/$BR"

# 3. A PR exists for this branch
gh pr view --json url,state --jq '"OK pr: \(.url) [\(.state)]"' \
  || echo "FAIL: no PR — run: gh pr create"

# 4. The spec carries the PR back (loop closed, both directions)
grep -q "^\*\*PR\*\*:" "specs/$BR/spec.md" 2>/dev/null \
  && echo "OK spec stamped with PR" \
  || echo "FAIL: specs/$BR/spec.md has no **PR**: line — run: /kb-spec post"

# 5. Repo can actually receive a PR
git remote get-url origin >/dev/null 2>&1 \
  || echo "BLOCKED: no git remote — no PR is possible until one exists"
```

Check 5 is not hypothetical: several local projects (`tokyo`, `up`, `vrcd`, `xavork-saas`, `law`, `software-factory`) have **no remote**, so every PR step silently cannot run there. Report that as blocked rather than claiming success.

For a large change, split it with `gh stack` instead of one giant PR — the `gh-stack` skill is installed.

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

## Invocation (English + Arabic)

| Trigger phrase (EN)                | Trigger phrase (AR)                          | What kb-dev does                                                  |
|------------------------------------|----------------------------------------------|-------------------------------------------------------------------|
| "new feature X"                    | "ميزة جديدة X" / "خاصية جديدة X"             | Run phases 0 → 2a → 4, pause for solo/fan-out decision            |
| "build X" / "implement X"          | "ابني X" / "اعمل X" / "نفّذ X" / "صنع X"     | Run phases 0 → 12 (full pipeline)                                 |
| "implement the spec at specs/NNN"  | "نفّذ المواصفات في specs/NNN"                | Run phase 0, then jump to phase 5, then 6–12                      |
| "fix bug Y" (< 30 LOC)             | "أصلح خطأ Y" / "صلح Y" / "إصلاح Y"           | Run phase 0, then solo-mode phase 5a straight through to 12       |
| "ship this branch"                 | "انشر هذا الفرع" / "إطلاق"                   | Run phases 9 → 12                                                 |
| "debug this"                       | "صحح هذا" / "ابحث عن المشكلة"                | Run `systematic-debugging` directly                               |
| "brainstorm X"                     | "فكّر في X" / "اقتراحات لـ X"                | Run `brainstorming` directly                                      |
| "spec out X" / "write a spec for X"| "اكتب مواصفات X" / "حدد X"                   | Run `kb-spec` standalone (phases 0,2,3,4 only — no implementation)|

**Language note:** I (Claude) understand Arabic natively. Even prompts in mixed Arabic/English/French route correctly based on semantic content, not just keyword matching. The hook regex covers the most common Arabic engineering vocabulary as a safety net.

## What kb-dev explicitly does NOT do

- It does not rewrite `kb-spec`, `kb-query`, or any other sub-skill. It only sequences them.
- It does not replace `/speckit.*`. Spec Kit still owns spec/plan/tasks file authoring. kb-dev just wires the KB research steps before each Spec Kit call and the knowledge capture after.
- It does not silently run destructive operations. Merging, force-pushing, dropping migrations, deleting branches — all pause for user confirmation regardless of the current phase.

## Relationship to the standing-rule hook

The global `UserPromptSubmit` hook at `~/.claude/hooks/user-prompt-kb-check.sh` already reminds you to run `/kb-query` and `/kb-spec <phase>` before each matching action. kb-dev is the **explicit** codification of that rule as a complete skill — use it when the user wants "the whole pipeline" instead of cherry-picking phases manually.

## Connect-the-dots: skill relations map

This is the canonical map of how all 39 installed skills relate to each other. kb-dev is the hub — every other skill is reachable through one of its phases or as an explicit standalone branch. The per-edge list lives at [`docs/CONNECTIONS.md`](../../docs/CONNECTIONS.md); the human-readable extract lives at [`docs/RELATIONS.md`](../../docs/RELATIONS.md).

```
                              ┌─────────────────────────┐
                              │   USER PROMPT (any)     │
                              └────────────┬────────────┘
                                           │
                          ┌────────────────┴────────────────┐
                          │  UserPromptSubmit hook fires    │
                          │  - bootstraps git/kb/speckit    │
                          │  - injects standing-rule reminder│
                          └────────────────┬────────────────┘
                                           │
              ┌────────────────────────────┼────────────────────────────┐
              │                            │                            │
              ▼                            ▼                            ▼
    ┌──────────────────┐       ┌──────────────────────┐     ┌──────────────────┐
    │ trivial Q/cmd    │       │  spec-only request   │     │ feature/build/   │
    │ (no skills)      │       │  "spec out X"        │     │ ship/fix request │
    └──────────────────┘       └─────────┬────────────┘     └────────┬─────────┘
                                         │                           │
                                         ▼                           ▼
                              ┌────────────────────┐       ┌──────────────────┐
                              │   /kb-spec only    │       │     /kb-dev      │
                              │ (phases 0,2,3,4)   │       │  (full pipeline) │
                              └─────────┬──────────┘       └────────┬─────────┘
                                        │                           │
                                        └─────────────┬─────────────┘
                                                      │
                                                      ▼
              ┌──────────────────────────────────────────────────────────────┐
              │                  Phase 0: /kb-query                          │
              │  → cites [[wikilinks]] from prior decisions                  │
              └──────────────────────────────┬───────────────────────────────┘
                                             │
                                             ▼
              ┌──────────────────────────────────────────────────────────────┐
              │            Phase 1: brainstorming (obra)                     │
              │  → option exploration, before committing to a direction     │
              └──────────────────────────────┬───────────────────────────────┘
                                             │
                                             ▼
              ┌──────────────────────────────────────────────────────────────┐
              │   Phase 2: /kb-spec pre  →  /speckit.specify  →  spec.md     │
              └──────────────────────────────┬───────────────────────────────┘
                                             │
                                             ▼
              ┌──────────────────────────────────────────────────────────────┐
              │   Phase 2a: Research — researcher (read-only + web)         │
              │   → specs/NNN/research.md (KB prior art, library docs for   │
              │     repo versions, 2-3 competitors with URLs, risks)        │
              │   Mandatory before Phase 3 design decisions.                │
              └──────────────────────────────┬───────────────────────────────┘
                                             │
                                             ▼
              ┌──────────────────────────────────────────────────────────────┐
              │  Phase 3: /kb-spec plan  →  /speckit.plan                    │
              │           →  writing-plans (obra)  →  plan.md                │
              └──────────────────────────────┬───────────────────────────────┘
                                             │
                                             ▼
              ┌──────────────────────────────────────────────────────────────┐
              │  Phase 4: /kb-spec tasks  →  /speckit.tasks  →  tasks.md     │
              └──────────────────────────────┬───────────────────────────────┘
                                             │  AUTO-CONTINUE
                                             ▼
                          ┌──────────────────────────────────┐
                          │  Compute NIU. Decide:            │
                          │  NIU = 1  →  solo                │
                          │  NIU ≥ 2  →  fan-out             │
                          └────────┬────────────────┬────────┘
                                   │                │
                          ┌────────┘                └────────┐
                          ▼                                   ▼
              ┌──────────────────────┐         ┌──────────────────────────────┐
              │ Phase 5a: SOLO       │         │ Phase 5b: FAN-OUT            │
              │ executing-plans      │         │ Main-session orchestrator    │
              │ in current session   │         │  ↓                           │
              │ Sonnet               │         │ dispatching-parallel-agents  │
              └──────────┬───────────┘         │  ↓                           │
                         │                     │ N × Sonnet workers           │
                         │                     │  each running:               │
                         │                     │  subagent-driven-development │
                         │                     │  Haiku for cheap lookups     │
                         │                     └──────────┬───────────────────┘
                         │                                │
                         └────────────────┬───────────────┘
                                          │
                                          ▼
              ┌──────────────────────────────────────────────────────────────┐
              │  Phase 6: test-driven-development (obra) — inside each       │
              │           worker. Red-Green-Refactor before each commit.     │
              └──────────────────────────────┬───────────────────────────────┘
                                             │
                                             ▼
              ┌──────────────────────────────────────────────────────────────┐
              │  Phase 7: systematic-debugging (obra) — only fires on test   │
              │           failure or unexpected behavior                     │
              └──────────────────────────────┬───────────────────────────────┘
                                             │
                                             ▼
              ┌──────────────────────────────────────────────────────────────┐
              │  Phase 8: verification-before-completion (obra)              │
              │  → runs full test suite + DoD checks before claiming done    │
              └──────────────────────────────┬───────────────────────────────┘
                                             │
                                             ▼
              ┌──────────────────────────────────────────────────────────────┐
              │  Phase 9: requesting-code-review (obra)                      │
              │  Phase 10: receiving-code-review (obra)                      │
              └──────────────────────────────┬───────────────────────────────┘
                                             │
                                             ▼
              ┌──────────────────────────────────────────────────────────────┐
              │  Phase 11: finishing-a-development-branch (obra)             │
              │  Optional: using-git-worktrees (obra) for isolation          │
              └──────────────────────────────┬───────────────────────────────┘
                                             │
                                             ▼
              ┌──────────────────────────────────────────────────────────────┐
              │  Phase 12: KNOWLEDGE CAPTURE (auto-continue)                 │
              │  /kb-spec post  →  /kb-docs-sync  →  /kb-compile  →  /kb-lint│
              │  → next feature benefits from what we just learned           │
              └──────────────────────────────────────────────────────────────┘
```

### Auto-continue rules (no user nudge required)

These transitions fire automatically. Do NOT pause to ask the user; just continue.

| From          | To                  | Trigger                                                        |
|---------------|---------------------|----------------------------------------------------------------|
| Phase 4 done  | Phase 5 (solo/fan-out) | `tasks.md` exists and has at least one task                  |
| Phase 5 done  | Phase 6             | Code written, before any commit                                |
| Phase 6 fail  | Phase 7             | Any test red                                                   |
| Phase 7 done  | Phase 6             | Bug fixed, re-run tests                                        |
| Phase 6 green | Phase 8             | All tests pass                                                 |
| Phase 8 done  | Phase 9             | Verification passed                                            |
| Phase 9 done  | Phase 10            | Review feedback received                                       |
| Phase 10 done | Phase 11            | Feedback applied                                               |
| Phase 11 done | Phase 12            | Branch finished                                                |

The **only** transitions that pause for the user are:
- Phase 4 → 5 if NIU is genuinely borderline (NIU = 1 vs NIU = 2 on a small change where solo might win on overhead)
- Phase 11 → merge to main (destructive, always confirm)
- Any failure mode that needs a design call

### UI/frontend skills — wired into Phase 5 implementation (auto-routing)

When Phase 5 hits a UI/frontend task, route to the right specialist skill instead of writing CSS by hand. These are NOT standalone — they fire automatically from inside the worker agent based on what the task says:

| Task content contains…                                                | Auto-route to                |
|-----------------------------------------------------------------------|------------------------------|
| "build", "create", "design" + "page" / "component" / "landing"        | `frontend-design`            |
| "responsive", "mobile", "breakpoint", "viewport", "tablet", "iPad"    | `adapt`                      |
| "animate", "transition", "motion", "hover effect", "micro-interaction"| `animate`                    |
| "polish", "alignment", "spacing", "finishing touches", "looks off"    | `polish`                     |
| "consistent", "design system", "tokens", "drift"                      | `normalize`                  |
| "harden", "edge case", "i18n", "overflow", "production-ready"         | `harden`                     |
| "slow", "laggy", "janky", "bundle size", "perf"                       | `optimize`                   |
| "a11y", "accessibility", "audit", "lighthouse"                        | `audit`                      |
| "confusing copy", "label", "error message", "microcopy"               | `clarify`                    |
| "too bold", "too loud", "calmer", "overstimulating"                   | `quieter`                    |
| React / Next.js component or perf work                                | `vercel-react-best-practices`|
| website page / form / user flow (search, booking, cart, contact)     | `webmcp` (register tools for the flow's public actions) |

These routing rules apply both to **solo mode** (Phase 5a — current session) and **fan-out mode** (Phase 5b — each Sonnet worker spawns the relevant UI skill inside its own context). The orchestrator does not need to invoke them; the worker recognizes its task and pulls in the matching skill.

### Standalone branches (only on explicit user invocation)

These never auto-fire from kb-dev — the user must explicitly request them:

| Skill               | Trigger                                              | Why standalone                            |
|---------------------|------------------------------------------------------|-------------------------------------------|
| `grill-me`          | "grill me", "stress-test this", "poke holes"         | High-friction; opt-in only                |
| `tech-company`      | "act as a tech company", "delegate to engineers"     | Alternative orchestrator pattern          |
| `caveman`           | "caveman lite/full/ultra", "talk like caveman", "terse mode" | Output-style modifier — must opt in so it doesn't fight kb-* citation rules |
| `design-check`      | "check the design", "audit the theme", "is our theme respected" | Read-only conformance scan; hands off to `/normalize` for fixes |
| `design-md`         | "use the Linear aesthetic", "apply the Stripe design" | Adopts an external brand design system into the project |
| `kb-ingest`         | "ingest these docs", file dropped in `raw/`          | Manual document ingest                    |
| `kb-publish`        | "publish KB to NotebookLM"                           | Manual publishing                         |
| `kb-lint`           | "audit the KB", periodic on demand                   | Audit, not workflow                       |
| `writing-skills`    | "create a new skill", "edit a skill"                 | Skill authoring meta-tool                 |
| `using-superpowers` | Auto-loaded at session start by obra                 | Bootstrapper, not in pipeline             |

### Design workflow (chain of standalone skills)

When the user is working on a design/theme concern, the preferred chain is:

```
1. /design-md <brand>       (optional — adopt a brand's design system)
2. /design-check             (scan for conflicts against the theme — read-only)
3. /normalize <scope>        (apply the fixes design-check identified)
4. /polish                   (micro-polish pixel-level details)
5. /audit                    (technical quality: a11y, perf, responsive)
6. /finishing-a-development-branch  (ship it)
```

`design-check` auto-offers to invoke `/normalize` at the end of its scan — the user does not need to type both commands unless they decline the handoff. This is the theme-consistency loop that closes the "all UI should fetch the main design, with fix for gaps" requirement.

### Cross-references (which skill calls which)

- `kb-dev` calls everything in the main pipeline.
- `kb-spec` calls `kb-query` (reads prior art) and `kb-docs-sync` (in `post` mode).
- `dispatching-parallel-agents` calls the `Agent` tool with `subagent-driven-development` loaded into each worker.
- `executing-plans` calls `test-driven-development` for each task and `verification-before-completion` at the end.
- `requesting-code-review` reads the diff and writes a review request; `receiving-code-review` reads incoming feedback and routes it back to `executing-plans` for fixes.
- `kb-compile` reads `daily/` logs (auto-captured by the SessionStart hook) and writes to `knowledge/concepts/` + `knowledge/connections/`.
- `kb-docs-sync` mirrors `specs/`, `plans/`, `CLAUDE.md`, `README.md` into `knowledge/sources/`.
- `design-md` downloads a brand `DESIGN.md` and chains into `design-check` for conformance.
- `design-check` reports mismatches against the adopted design system and hands off to `normalize` for fixes.
- `normalize` → `polish` → `audit` is the design workflow tail (see "Design workflow" section above).
- `brainstorming` is the phase-1 gate; every skill path that goes through phase 5 first touches brainstorming unless the user explicitly jumps to "implement the spec at specs/NNN".

### Complete handoff matrix (39 skills; `kb-spec` is one skill with four phases)

This table lets any skill know where it sits in the graph without reading the full pipeline.

| Skill                             | Triggered by (upstream)                             | Hands off to (downstream)                        | Auto/Manual |
|-----------------------------------|-----------------------------------------------------|--------------------------------------------------|-------------|
| `kb-dev`                          | USER keywords: build/implement/ship/fix             | kb-query (phase 0)                               | manual      |
| `kb-query`                        | kb-dev phase 0, kb-spec all phases, any history Q   | brainstorming (in pipeline) / answer (standalone)| **auto**    |
| `brainstorming`                   | kb-dev phase 1, USER "brainstorm X"                 | kb-spec pre                                      | **auto**    |
| `kb-spec pre`                     | brainstorming, kb-dev phase 2                       | /speckit.specify                                 | **auto**    |
| `kb-spec plan`                    | /speckit.specify done, kb-dev phase 3               | /speckit.plan → writing-plans                    | **auto**    |
| `writing-plans`                   | kb-spec plan / /speckit.plan                        | kb-spec tasks                                    | **auto**    |
| `kb-spec tasks`                   | writing-plans, kb-dev phase 4                       | /speckit.tasks → solo/fan-out decision           | **auto**    |
| `executing-plans`                 | kb-dev phase 5a, receiving-code-review fix loop     | TDD, UI specialists (phase 5 auto-route)         | **auto**    |
| `dispatching-parallel-agents`     | kb-dev phase 5b                                     | N × subagent-driven-development                  | **auto**    |
| `subagent-driven-development`     | dispatching-parallel-agents                         | TDD, UI specialists                              | **auto**    |
| `test-driven-development`         | executing-plans / subagent-driven-development       | systematic-debugging (fail) / verification (green)| **auto**    |
| `systematic-debugging`            | TDD failure, USER "debug this"                      | TDD (re-run)                                     | **auto**    |
| `verification-before-completion`  | TDD green                                           | requesting-code-review                           | **auto**    |
| `requesting-code-review`          | verification-before-completion                      | receiving-code-review                            | **auto**    |
| `receiving-code-review`           | requesting-code-review                               | executing-plans (fix) OR finishing-branch        | **auto**    |
| `using-git-worktrees`             | kb-dev phase 11 (optional)                          | finishing-a-development-branch                   | manual      |
| `finishing-a-development-branch`  | receiving-code-review, audit, worktrees             | kb-spec post (PAUSE before merge)                | **auto**    |
| `kb-spec post`                    | finishing-a-development-branch, kb-dev phase 12     | kb-docs-sync                                     | **auto**    |
| `kb-docs-sync`                    | kb-spec post                                        | kb-compile                                       | **auto**    |
| `kb-compile`                      | kb-docs-sync, session end                           | kb-lint                                          | **auto**    |
| `kb-lint`                         | kb-compile, USER "audit KB"                         | — (terminal)                                     | **auto**    |
| `kb-setup`                        | USER / auto-bootstrap hook on missing KB            | — (one-shot)                                     | **auto**    |
| `kb-ingest`                       | USER "ingest these docs" (STANDALONE ONLY)          | kb-compile (after write)                         | manual      |
| `kb-publish`                      | USER "publish KB" (STANDALONE ONLY)                 | — (terminal)                                     | manual      |
| `design-md`                       | USER "use X aesthetic" / "apply brand Y"            | design-check                                     | manual      |
| `design-check`                    | design-md, USER "check the design"                  | normalize (auto-offer)                           | manual      |
| `normalize`                       | design-check, phase 5 auto-route                    | polish                                           | **auto**    |
| `polish`                          | normalize, phase 5 auto-route                       | audit                                            | **auto**    |
| `audit`                           | polish, phase 5 auto-route                          | finishing-a-development-branch                   | **auto**    |
| `harden`                          | phase 5 auto-route                                  | test-driven-development                          | **auto**    |
| `optimize`                        | phase 5 auto-route                                  | verification-before-completion                   | **auto**    |
| `adapt`                           | phase 5 auto-route                                  | test-driven-development                          | **auto**    |
| `animate`                         | phase 5 auto-route                                  | polish                                           | **auto**    |
| `clarify`                         | phase 5 auto-route                                  | test-driven-development                          | **auto**    |
| `quieter`                         | phase 5 auto-route                                  | polish                                           | **auto**    |
| `frontend-design`                 | phase 5 auto-route                                  | polish → audit                                   | **auto**    |
| `vercel-react-best-practices`     | phase 5 auto-route                                  | optimize → verification-before-completion        | **auto**    |
| `grill-me`                        | USER "grill me" (STANDALONE ONLY)                   | writing-plans (if accepted)                      | manual      |
| `tech-company`                    | USER "act as tech company" (STANDALONE ONLY)        | (spawns role subagents)                          | manual      |
| `caveman`                         | USER "caveman lite/full/ultra" (STANDALONE ONLY)    | — (terminal output-style modifier)               | manual      |
| `writing-skills`                  | USER "create a new skill" (STANDALONE ONLY)         | — (meta)                                         | manual      |
| `using-superpowers`               | session start (auto)                                | (discovery only, no pipeline)                    | **auto**    |

**Reading the "Auto/Manual" column:** "auto" means the skill fires without user confirmation once its upstream edge is triggered. "Manual" means the user must explicitly invoke it — either because it's standalone (grill-me, tech-company, kb-ingest, kb-publish) or because it has a meaningful design decision attached (kb-dev entry, design-md brand choice, using-git-worktrees).

This is the complete map. If a skill is not on it, it is either a meta-tool or a user-utility (loop, schedule, update-config, keybindings-help) and is not part of the dev pipeline.
