# kb-dev complete handoff matrix (split from skill-map.md 2026-10-27; fan-out / tech-company rows are retired)

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
| `system-ux`                       | phase 2c (new apps) + phase 5 auto-route (UI work)  | system-design / design-md → frontend-design      | **auto**    |
| `frontend-design`                 | phase 5 auto-route                                  | polish → audit                                   | **auto**    |
| `vercel-react-best-practices`     | phase 5 auto-route                                  | optimize → verification-before-completion        | **auto**    |
| `grill-me`                        | USER "grill me" (STANDALONE ONLY)                   | writing-plans (if accepted)                      | manual      |
| `tech-company`                    | USER "act as tech company" (STANDALONE ONLY)        | (spawns role subagents)                          | manual      |
| `caveman`                         | USER "caveman lite/full/ultra" (STANDALONE ONLY)    | — (terminal output-style modifier)               | manual      |
| `writing-skills`                  | USER "create a new skill" (STANDALONE ONLY)         | — (meta)                                         | manual      |
| `using-superpowers`               | session start (auto)                                | (discovery only, no pipeline)                    | **auto**    |

**Reading the "Auto/Manual" column:** "auto" means the skill fires without user confirmation once its upstream edge is triggered. "Manual" means the user must explicitly invoke it — either because it's standalone (grill-me, tech-company, kb-ingest, kb-publish) or because it has a meaningful design decision attached (kb-dev entry, design-md brand choice, using-git-worktrees).

This is the complete map. If a skill is not on it, it is either a meta-tool or a user-utility (loop, schedule, update-config, keybindings-help) and is not part of the dev pipeline.
