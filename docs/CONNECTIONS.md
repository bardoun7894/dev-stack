# dev-stack — canonical skill connection graph

This is the single source of truth for **every edge** between skills in dev-stack.
When you add, rename, or remove a skill, update this file first — then mirror the
change into `docs/RELATIONS.md`, `skills/kb-dev/SKILL.md`, and the affected
individual `SKILL.md` descriptions.

## Node list (40 skills)

| ID                              | Tier         | Role                                 |
|---------------------------------|--------------|--------------------------------------|
| `kb-dev`                        | first-party  | Pipeline hub (12-phase orchestrator) |
| `market-swot`                   | first-party  | SWOT + competitor + UI/UX research   |
| `grill-me`                      | first-party  | Adversarial planner (standalone)     |
| `system-design`                 | first-party  | Architecture doc + owner approval stop |
| `design-check`                  | first-party  | Design conformance scanner           |
| `design-md`                     | first-party  | Brand design system adopter          |
| `caveman`                       | first-party  | Output-style modifier (standalone)   |
| `kb-setup`                      | kb-skill     | Bootstrap KB in a project            |
| `kb-query`                      | kb-skill     | Ground answer in prior knowledge     |
| `kb-spec`                       | kb-skill     | Spec Kit ↔ KB bridge                 |
| `kb-ingest`                     | kb-skill     | Manual raw/ ingest                   |
| `kb-compile`                    | kb-skill     | daily/ → concepts/ compiler          |
| `kb-docs-sync`                  | kb-skill     | Mirror project docs into KB          |
| `kb-publish`                    | kb-skill     | KB → NotebookLM                      |
| `kb-lint`                       | kb-skill     | KB health audit                      |
| `brainstorming`                 | superpowers  | Intent/design exploration            |
| `writing-plans`                 | superpowers  | Spec → step-by-step plan             |
| `executing-plans`               | superpowers  | Solo in-session execution            |
| `dispatching-parallel-agents`   | superpowers  | Fan-out to independent workers       |
| `subagent-driven-development`   | superpowers  | Per-worker TDD loop                  |
| `test-driven-development`       | superpowers  | Red-Green-Refactor                   |
| `systematic-debugging`          | superpowers  | Root-cause on test failure           |
| `verification-before-completion`| superpowers  | Evidence before "done"               |
| `requesting-code-review`        | superpowers  | Dispatch review subagent             |
| `receiving-code-review`         | superpowers  | Technically rigorous response        |
| `finishing-a-development-branch`| superpowers  | Merge/PR/cleanup                     |
| `using-git-worktrees`           | superpowers  | Isolated worktree setup              |
| `writing-skills`                | superpowers  | Skill authoring                      |
| `using-superpowers`             | superpowers  | Session-start bootstrapper           |
| `frontend-design`               | vendor-local | Production-grade UI generation       |
| `vercel-react-best-practices`   | vendor-local | React/Next.js perf patterns          |
| `tech-company`                  | vendor-local | Persona-based parallel orchestrator  |
| `audit`                         | vendor-local | A11y/perf/theming report             |
| `harden`                        | vendor-local | Edge cases / i18n / overflow         |
| `polish`                        | vendor-local | Pixel-level micro-polish             |
| `normalize`                     | vendor-local | Realign UI to design system          |
| `optimize`                      | vendor-local | Perf fix                             |
| `animate`                       | vendor-local | Motion & micro-interactions          |
| `quieter`                       | vendor-local | Tone down aggressive design          |
| `adapt`                         | vendor-local | Responsive/cross-device              |
| `clarify`                       | vendor-local | UX copy improvement                  |

## Edge list (who calls whom)

Format: `from → to [trigger]`. Edges are grouped by the layer where they fire.

### Entry layer (user prompt → first skill)

```
USER                         → kb-dev           [build / implement / ship / fix / new feature / refactor]
USER                         → kb-spec          [spec out / write a spec / draft a plan / specify]
USER                         → kb-query         [what did we decide / how did we / any history question]
USER                         → brainstorming    [brainstorm / explore / idea / options]
USER                         → grill-me         [grill me / stress-test / poke holes — STANDALONE ONLY]
USER                         → tech-company     [act as a tech company — STANDALONE ONLY]
USER                         → design-md        [use the Linear aesthetic / apply brand X]
USER                         → design-check     [check the design / is theme respected]
USER                         → kb-setup         [set up knowledge base / install kb]
USER                         → kb-ingest        [ingest these docs — STANDALONE ONLY]
USER                         → kb-publish       [publish KB to NotebookLM — STANDALONE ONLY]
USER                         → kb-lint          [audit the KB — STANDALONE ONLY]
USER                         → writing-skills   [create a new skill — STANDALONE ONLY]
USER                         → using-superpowers [auto at session start]
USER                         → caveman          [caveman / talk like caveman / terse mode / compress output — STANDALONE ONLY]
```

### kb-dev pipeline (phases 0–12)

```
kb-dev                       → kb-query                          [phase 0 — ground]
kb-query                     → brainstorming                     [phase 0 → 1]
brainstorming                → kb-spec pre                       [phase 1 → 2]
kb-spec pre                  → /speckit.specify                  [phase 2 — spec authoring]
/speckit.specify             → system-design                     [phase 2 → 2c — new apps only]
kb-dev                       → system-design                     [phase 2c — hard stop for owner approval]
system-design                → fusion                            [one /opinion on load-bearing decisions]
system-design                → kb-spec plan                      [phase 2c → 3 — after owner approves D/Q codes]
/speckit.specify             → kb-spec plan                      [phase 2 → 3]
kb-spec plan                 → /speckit.plan                     [phase 3 — plan authoring]
/speckit.plan                → writing-plans                     [phase 3 — plan elaboration]
writing-plans                → kb-spec tasks                     [phase 3 → 4]
kb-spec tasks                → /speckit.tasks                    [phase 4 — task breakdown]
kb-dev                       → market-swot                       [phase 2b — market & UX research]
market-swot                  → web-search                        [competitor + fresh-practice search]
market-swot                  → dribbble-design                   [UI/UX reference shots]
market-swot                  → jev                               [score/choice ranking]
market-swot                  → kb-spec                           [accepted F/R codes -> pre / research.md]
market-swot                  → agy-delegate                      [accepted UI items]
/speckit.tasks               → kb-dev (decision: solo vs fan-out)[phase 4 → 5]

kb-dev                       → executing-plans                   [phase 5a — solo, ≤3 tasks]
kb-dev                       → dispatching-parallel-agents       [phase 5b — fan-out, ≥4 tasks]
dispatching-parallel-agents  → subagent-driven-development       [per-worker]
executing-plans              → test-driven-development           [phase 5 → 6]
subagent-driven-development  → test-driven-development           [per-worker, phase 5 → 6]
test-driven-development      → systematic-debugging              [phase 6 → 7 — ONLY ON FAILURE]
systematic-debugging         → test-driven-development           [phase 7 → 6 — re-run]
test-driven-development      → verification-before-completion    [phase 6 → 8 — tests green]

verification-before-completion → requesting-code-review          [phase 8 → 9]
requesting-code-review       → receiving-code-review             [phase 9 → 10]
receiving-code-review        → executing-plans                   [phase 10 — fix loop]
receiving-code-review        → finishing-a-development-branch    [phase 10 → 11]
using-git-worktrees          → finishing-a-development-branch    [optional isolation]
finishing-a-development-branch → kb-spec post                    [phase 11 → 12 — PAUSE before merge]

kb-spec post                 → kb-docs-sync                      [phase 12 — mirror]
kb-docs-sync                 → kb-compile                        [phase 12]
kb-compile                   → kb-lint                           [phase 12 — final audit]
```

### UI specialist auto-routing (inside phase 5)

These edges fire **inside** a worker (solo or fan-out) when its task description matches:

```
executing-plans              → frontend-design    [build / create / design + page/component/landing]
executing-plans              → adapt              [responsive / mobile / breakpoint / viewport]
executing-plans              → animate            [animate / transition / motion / hover]
executing-plans              → polish             [polish / alignment / spacing / looks off]
executing-plans              → normalize          [consistent / design system / tokens / drift]
executing-plans              → harden             [harden / edge case / i18n / overflow]
executing-plans              → optimize           [slow / laggy / janky / bundle size]
executing-plans              → audit              [a11y / accessibility / lighthouse]
executing-plans              → clarify            [confusing copy / label / error message]
executing-plans              → quieter            [too bold / too loud / calmer]
executing-plans              → vercel-react-best-practices  [React/Next.js perf]
subagent-driven-development  → (same set)        [fan-out workers use the same routing table]
```

### Design workflow chain (standalone, theme-consistency loop)

```
design-md <brand>            → design-check       [after adoption, verify conformance]
design-check                 → normalize          [auto-offers handoff for fixes]
normalize                    → polish             [after structural fixes, polish details]
polish                       → audit              [after polish, final quality pass]
audit                        → finishing-a-development-branch  [ship the theme pass]
```

### Meta layer

```
writing-skills               → (any new skill)    [skill authoring]
using-superpowers            → (all superpowers)  [session-start discovery]
kb-setup                     → (all kb-* skills)  [installs the entire kb layer]
```

## Upstream / downstream map (per skill)

For each skill: who hands off **to** it (upstream) and who it hands off **from** (downstream).
Skills with `—` in a column are pipeline endpoints or standalone-only.

| Skill                             | Upstream (who calls this)                         | Downstream (this calls)                         |
|-----------------------------------|---------------------------------------------------|-------------------------------------------------|
| `kb-dev`                          | USER                                              | kb-query, kb-spec, executing-plans, dispatching-parallel-agents |
| `kb-query`                        | USER, kb-dev (phase 0), kb-spec (all phases)      | brainstorming (inside kb-dev), — (standalone)  |
| `brainstorming`                   | kb-dev (phase 1), USER                            | kb-spec pre                                     |
| `kb-spec pre`                     | brainstorming, kb-dev (phase 2)                   | /speckit.specify                                |
| `system-design`                   | kb-dev (phase 2c), USER                           | fusion, kb-spec plan                            |
| `kb-spec plan`                    | /speckit.specify, system-design, kb-dev (phase 3)                | /speckit.plan, writing-plans                    |
| `writing-plans`                   | kb-spec plan, /speckit.plan                       | kb-spec tasks                                   |
| `kb-spec tasks`                   | writing-plans, kb-dev (phase 4)                   | /speckit.tasks                                  |
| `executing-plans`                 | kb-dev (phase 5a), receiving-code-review (fix loop)| test-driven-development, UI specialists       |
| `dispatching-parallel-agents`     | kb-dev (phase 5b)                                 | subagent-driven-development (× N workers)       |
| `subagent-driven-development`     | dispatching-parallel-agents                       | test-driven-development, UI specialists         |
| `test-driven-development`         | executing-plans, subagent-driven-development      | systematic-debugging (fail) OR verification-before-completion (green) |
| `systematic-debugging`            | test-driven-development, USER ("debug this")      | test-driven-development (re-run)                |
| `verification-before-completion`  | test-driven-development                           | requesting-code-review                          |
| `requesting-code-review`          | verification-before-completion                    | receiving-code-review                           |
| `receiving-code-review`           | requesting-code-review                            | executing-plans (fix) OR finishing-a-development-branch |
| `using-git-worktrees`             | kb-dev (phase 11, optional)                       | finishing-a-development-branch                  |
| `finishing-a-development-branch`  | receiving-code-review, using-git-worktrees, audit | kb-spec post                                    |
| `kb-spec post`                    | finishing-a-development-branch, kb-dev (phase 12) | kb-docs-sync                                    |
| `kb-docs-sync`                    | kb-spec post                                      | kb-compile                                      |
| `kb-compile`                      | kb-docs-sync                                      | kb-lint                                         |
| `kb-lint`                         | kb-compile, USER                                  | — (pipeline end)                                |
| `kb-setup`                        | USER, auto-bootstrap hook                         | — (one-shot)                                    |
| `kb-ingest`                       | USER (standalone only)                            | — (runs kb-compile on write)                    |
| `kb-publish`                      | USER (standalone only)                            | — (one-shot)                                    |
| `design-md`                       | USER                                              | design-check                                    |
| `design-check`                    | design-md, USER                                   | normalize                                       |
| `normalize`                       | design-check, executing-plans (phase 5 auto-route)| polish                                          |
| `polish`                          | normalize, executing-plans (phase 5 auto-route)   | audit                                           |
| `audit`                           | polish, executing-plans (phase 5 auto-route)      | finishing-a-development-branch                  |
| `harden`                          | executing-plans (phase 5 auto-route)              | test-driven-development                         |
| `optimize`                        | executing-plans (phase 5 auto-route)              | verification-before-completion                  |
| `adapt`                           | executing-plans (phase 5 auto-route)              | test-driven-development                         |
| `animate`                         | executing-plans (phase 5 auto-route)              | polish                                          |
| `clarify`                         | executing-plans (phase 5 auto-route)              | test-driven-development                         |
| `quieter`                         | executing-plans (phase 5 auto-route)              | polish                                          |
| `frontend-design`                 | executing-plans (phase 5 auto-route)              | polish, audit                                   |
| `vercel-react-best-practices`     | executing-plans (phase 5 auto-route)              | optimize, verification-before-completion        |
| `grill-me`                        | USER (STANDALONE ONLY)                            | writing-plans (if user accepts)                 |
| `tech-company`                    | USER (STANDALONE ONLY)                            | (spawns role subagents — alternative to fan-out)|
| `caveman`                         | USER (STANDALONE ONLY)                            | — (terminal output-style modifier)              |
| `writing-skills`                  | USER (STANDALONE ONLY)                            | — (meta)                                        |
| `using-superpowers`               | session start (auto)                              | (all superpowers skills — discovery only)      |

## The agent layer (8 registered subagents)

Skills live in `~/.claude/skills/`. **Agents** live in `~/.claude/agents/` and are spawned via the `Agent` tool with `subagent_type: "<name>"`. The orchestrator dispatches workers; each worker loads a curated set of skills on startup.

| Agent              | Default model | Loads on startup (skills)                                                                                                  |
|--------------------|---------------|----------------------------------------------------------------------------------------------------------------------------|
| `orchestrator`     | opus          | (no skill loads — pure dispatch)                                                                                           |
| `planner`          | sonnet        | (none — produces tasks.md only)                                                                                            |
| `frontend-engineer`| sonnet        | test-driven-development, frontend-design, polish, animate, adapt, normalize, harden, optimize, audit, clarify, quieter, vercel-react-best-practices, verification-before-completion |
| `backend-engineer` | sonnet        | test-driven-development, verification-before-completion, systematic-debugging                                              |
| `qa-engineer`      | sonnet        | test-driven-development, verification-before-completion, systematic-debugging                                              |
| `debugger`         | sonnet→opus   | systematic-debugging, test-driven-development, verification-before-completion                                              |
| `designer`         | sonnet        | design-md, design-check, normalize, polish, audit, test-driven-development, verification-before-completion                 |
| `reviewer`         | sonnet        | requesting-code-review, receiving-code-review                                                                              |

### Agent dispatch edges

```
USER                         → kb-dev / orchestrator     [build / implement / ship / fix]
kb-dev (parent is opus)      → orchestrator (in-session, no spawn)  [phase 5b]
kb-dev (parent is sonnet)    → Agent(orchestrator, opus)            [phase 5b — spawn separate Opus]
orchestrator                 → Agent(planner, sonnet)               [no tasks.md → derive one]
orchestrator                 → Agent(frontend-engineer, sonnet)     [packet has UI/CSS/React]
orchestrator                 → Agent(backend-engineer, sonnet)      [packet has API/DB/server]
orchestrator                 → Agent(qa-engineer, sonnet)           [packet has test work]
orchestrator                 → Agent(debugger, sonnet|opus)         [packet has bug/failure]
orchestrator                 → Agent(designer, sonnet)              [packet has design system / theme]
orchestrator                 → Agent(reviewer, sonnet)              [phase 9 — final review]
orchestrator                 → Agent(general-purpose, haiku)        [trivial one-shot lookups]
```

Each spawned worker runs in **its own context window**. When it returns, the orchestrator only sees the worker's ~200-word report — not the full transcript. This is the ~100× context efficiency win.

### Model selection by complexity

| Class | Model | LOC | Files | Examples |
|-------|-------|-----|-------|----------|
| trivial | haiku | 0 | 0-1 | "Does foo exist in bar.ts?", "What's the value of MAX_RETRIES?" |
| simple | sonnet | <100 | 1-2 | Add a button, fix a typo'd label, one new test case |
| medium | sonnet | 100-500 | 3-10 | New API endpoint with tests, refactor a service class, fix a non-trivial bug |
| hard | opus | 500+ | 10+ | Auth migration, race-condition debugging without a clear hypothesis, novel architecture |

The full classifier lives in `~/code/dev-stack/agents/orchestrator.md`.

## Invariants

1. **Every skill has at least one upstream edge** (either USER or another skill). No orphans.
2. **Every pipeline skill has at least one downstream edge.** Only standalone skills (`kb-lint`, `kb-setup`, `kb-ingest`, `kb-publish`, `writing-skills`, `using-superpowers`, `caveman`) end the chain.
3. **`grill-me`, `tech-company`, and `caveman` have no incoming pipeline edges** — they fire only on explicit USER invocation.
4. **The design workflow chain terminates at `finishing-a-development-branch`** — same terminal as the main pipeline.
5. **Phase 5 UI specialists always loop back** into `test-driven-development` or `verification-before-completion`, never exit sideways.
6. **`caveman` is a parallel modifier**, not a phase. It applies to output style without changing the pipeline graph. It must SUSPEND itself in: kb-query results, kb-spec phase output, spec.md/plan.md/tasks.md authoring, verification-before-completion evidence, both code-review skills, systematic-debugging analysis, and all kb-compile/kb-lint/kb-docs-sync writes.
7. **Fan-out fires at NIU ≥ 2.** The previous threshold of 4 was wrong. The kb-dev hub and the orchestrator now both enforce 2.
8. **The current-session model determines whether to spawn a separate orchestrator subagent.** If the current session is Opus, the session IS the orchestrator (no spawn). If Sonnet/Haiku, spawn the Opus orchestrator subagent first.
9. **Trivial lookups go to Haiku, not Sonnet.** Anything that is a one-shot factual query without code generation should use `Agent(model: "haiku", subagent_type: "general-purpose", ...)`. This saves ~10× cost vs. Sonnet for the same answer quality on factual tasks.
10. **Workers never recurse.** A spawned worker may not spawn another orchestrator. Only the parent session can.

When editing skills, verify these invariants hold. `/kb-lint` (when run on this file's front-matter) will flag orphans.
