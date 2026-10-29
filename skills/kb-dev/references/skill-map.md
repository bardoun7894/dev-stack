# kb-dev skill relations, auto-routing and handoff matrix (moved from SKILL.md 2026-10-27; entries mentioning fan-out / dispatching-parallel-agents / tech-company are retired)

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
              │   Phase 2c: System design — system-design skill             │
              │   → specs/NNN/system-design.md (D-codes, Q-codes, diagrams) │
              │   HARD STOP: owner approves. New projects + new-infra work. │
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

