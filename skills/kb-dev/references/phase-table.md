# kb-dev phase table (moved from SKILL.md 2026-10-27, verbatim; phases 5a/5b replaced by the implementer loop)

| Phase                      | Sub-skill                                                                              | Model          |
|----------------------------|----------------------------------------------------------------------------------------|----------------|
| 0. Ground in prior art     | `/kb-query`                                                                            | (no agent)     |
| Jev down (402 / out of quota) | Nothing to change: `jev` and `jdelegate` fall back to local Laya (`laya-serve`, `engine: laya`, every `--min` gate fails closed); `jev-browse` and `jev-review` stay on Jev only and exit 3, so phase 8/9 use their normal LLM path. See `skills/jev/SKILL.md` "Local fallback: Laya" | auto |
| 1. Brainstorm options      | `brainstorming` (obra)                                                                 | inline         |
| 2. Pre-spec KB research    | `/kb-spec pre` → `/speckit.specify`                                                    | inline         |
| 2a. Research (mandatory)   | `jdelegate --no-auto-mcp --no-auto-skill --no-auto-role --role researcher` (one pass, read-only) → `specs/NNN/research.md` | Sonnet (read-only + web) |
| 2c. System design          | `system-design` → `specs/NNN/system-design.md`, check.sh gate; HARD STOP for owner approval of D/Q codes. New apps/projects only; skip for features in existing apps | inline         |
| 3. Architectural plan      | `/kb-spec plan` → `/speckit.plan` → `writing-plans` (obra)                             | inline         |
| 4. Task breakdown          | `/kb-spec tasks` → `/speckit.tasks`                                                    | inline         |
| 4b. **Branch (MANDATORY)** | **`git checkout -b <NNN-short-name>` — branch must match the spec dir. Never implement on `main`.** | inline |
| 5a. Implement (solo)       | `executing-plans` (obra) in current session                                            | Sonnet         |
| 5b. Implement (fan-out)    | `dispatching-parallel-agents` + `subagent-driven-development` (obra)                   | Opus → Sonnet  |
| 6. Test-first discipline   | `test-driven-development` (obra) inside each worker                                    | Sonnet         |
| 6a. Approve + lock checks | list checks in plain words → wait for user OK → `lock-checks approve <tests>` → loops/workers call `lock-checks verify` after each round; a failing verify = round undone | inline |
| 7. Debug if something fails| `systematic-debugging` (obra)                                                          | Sonnet         |
| 8. Verify before claiming  | `verification-before-completion` (obra); UI change → web: `jev-browse --flows` first (Jev System 1 agent, see `skills/jev/references/e2e-browsing.md`); mobile (Expo/RN): `npx e2e run` (see Phase 8: e2e suites) | Sonnet |
| 9. Request review          | `jev-review diff` first (System 1 screen): its `route` picks the reviewer alone, plus a Gemini 4 Argon second opinion (a Claude model verifies its findings), or plus `/panel`; then `requesting-code-review` (obra). No OpenAI/Codex (owner 2026-10-22) | Opus 5.5 xhigh |
| 9b. PR brief               | When opening the PR: `pr-pipeline` L3 brief (evidence, merge danger, diagram); L2 stays the existing `pr-review` bin. Diffs touching auth, payments or uploads also get `cso` | inline |
| 10. Apply review           | `receiving-code-review` (obra)                                                         | Sonnet         |
| 10b. Drift check           | `/direction` (`skills/direction`): report only, owner decides keep+update spec or revert. Run before phase 11 | inline |
| 11. Finish branch          | `finishing-a-development-branch` (obra) — **always ends in a PR** — optional: `using-git-worktrees` | inline |
| 12. Capture knowledge      | `/kb-spec post` → `/kb-docs-sync` → `/kb-compile` → `/kb-lint`                         | inline         |
