# kb-dev UI auto-routing, standalone skills, design chain (split from skill-map.md 2026-10-27)

### UI/frontend skills — wired into Phase 5 implementation (auto-routing)

When Phase 5 hits a UI/frontend task, route to the right specialist skill instead of writing CSS by hand. These are NOT standalone — they fire automatically from inside the worker agent based on what the task says:

| Task content contains…                                                | Auto-route to                |
|-----------------------------------------------------------------------|------------------------------|
| new app, dashboard, admin/ERP/CRM, form, user flow, nav/IA, UX audit  | `system-ux` (runs FIRST, before `frontend-design`) |
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
0. /system-ux               (AUTO — UX architecture, Object-Action Matrix, Inductive screens)
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

