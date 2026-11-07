# kb-dev phase table (moved from SKILL.md 2026-10-27, verbatim; phases 5a/5b replaced by the implementer loop)

| Phase                      | Sub-skill                                                                              | Model          |
|----------------------------|----------------------------------------------------------------------------------------|----------------|
| 0. Ground in prior art     | `/kb-query`                                                                            | (no agent)     |
| Jev down (402 / out of quota) | Nothing to change: `jev` and `jdelegate` fall back to local Laya (`laya-serve`, `engine: laya`, every `--min` gate fails closed); `jev-browse` and `jev-review` stay on Jev only and exit 3, so phase 8/9 use their normal LLM path. See `skills/jev/SKILL.md` "Local fallback: Laya" | auto |
| 1. Brainstorm options      | `brainstorming` (obra)                                                                 | inline         |
| 2. Pre-spec KB research    | `/kb-spec pre` → `/speckit.specify`                                                    | inline         |
| 2a. Research (mandatory)   | `jdelegate --no-auto-mcp --no-auto-skill --no-auto-role --role researcher` (one pass, read-only) → `specs/NNN/research.md` | Sonnet (read-only + web) |
| 2b. Market & UX research   | `market-swot project` — required for new products and UI-heavy features (new screens, redesign, landing pages), optional otherwise; feeds Phase 3 | inline + researcher |
| 2c. System design          | `system-design` → `specs/NNN/system-design.md`, check.sh gate (+ optional `/egm:egm-review` Goldfish comprehension/critic pass on high-risk designs); HARD STOP for owner approval of D/Q codes. New apps/projects only; skip for features in existing apps | inline         |
| 2d. EGM review (every spec) | every spec, automatic: Claude spawns the Agent subagent_type egm:egm-synthesizer on specs/NNN/spec.md (it runs the Goldfish reviewers in parallel and merges findings); tell it native Grep/Glob are denied, use mcp__lean-ctx__ctx_search/ctx_glob/ctx_tree. Show findings as F-codes; owner decides each; apply to spec.md before /kb-spec plan. agy/Codex: /egm:egm-review then /egm:egm-resolve. FAST LANE (no spec) skips. | Agent: egm:egm-synthesizer |
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

## EGM doc review (optional, between spec/design and `/kb-spec plan`; owner-approved 2026-11-06)

- When: only high-risk specs (auth, money, multi-service, new apps), after spec.md (and system-design.md for new apps), before `/kb-spec plan`. Also allowed for big features in existing apps, not only 2c. Never on FAST LANE or ordinary features.
- How: `/egm:egm-review specs/NNN/spec.md`, preset "Feature spec only"; for plan.md, preset "Implementation plan only". Never "Consolidated report" or the uninterrupted full flow. Put `EGM artifact directory: specs/NNN/egm` in the prompt.
- Cap: ONE review round. At every egm-review-loop checkpoint stop after round 1 (TOKEN BUDGET rule 6: max 1 review + 1 fix round). Reviewers run on the session model (Opus), so cost is real.
- Fixes: the main session (Elephant) checks every Goldfish PROPOSE FIX against owner rules before applying (Goldfish run with omitClaudeMd and do not know them). Then the owner approves D/Q codes as usual.
- Isolation is context-only: give Goldfish only spec/design file paths, never repo roots or .env.
- Do not use egm-brainstorm or egm-draft (brainstorming, `/kb-spec`, speckit and system-design cover them) or egm-drift-report (use `direction`). egm-bootstrap only on explicit owner request: filename EGM.md, one subtree, own branch.
- `reviewer` on the diff is unchanged; EGM reviews docs before code, not code.
- The plugin exists on the Mac and MyContabo only; on other hosts skip the EGM step and say so in one line.
