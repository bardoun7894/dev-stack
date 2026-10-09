# Gap Report Template

Use this template for `specs/_audit/<date>/gap-report.md`. Modeled on
`projects/board/specs/LUMIO-GAP-REPORT.md`.

## Header

```
# Gap Report — <Project Name>

Date: <YYYY-MM-DD>. Worktree: <branch>. Main inspected: <short SHA>.
Scope: <one sentence — what this audit covered>.
Original codes below are inventory counts and verified gaps, not promises
about implementation.
```

## Files Written

Bullet list of every artifact this run produced (research.md, new specs,
appended task blocks, ops notes). Use relative `[link](path)` form.

## Findings

For each gap, one row with these columns:

| Code | Source | Severity | Evidence | Verdict (after review) | Action |
|------|--------|----------|----------|------------------------|--------|
| G1   | PRD    | P1       | `backend/app/x.py:42` lacks `await` | Exists after N+1 | append tasks to spec NNN |
| G2   | checklist | P0    | `src/auth.ts` — no rate limit on login | confirmed | new spec |
| G3   | competitor | P2   | https://example.com/pricing — offers SSO, we don't | duplicate of 011 | drop |
| G4   | defect | P1     | `ai-knowledge-base/raw/abc.md` unresolved | confirmed | fix spec |
| G5   | spec   | P2     | spec 029 promises it; no implementation | confirmed | report only |

### Severity

- **P0** — blocks production. Fix before launch.
- **P1** — must fix soon. Visible to user or breaks contract.
- **P2** — should fix. Quality / competitive gap.
- **P3** — nit. Polish.

### Source

- `PRD` — from project's PRD doc
- `spec` — from project's own specs/ directory
- `checklist` — from `references/prod-checklist.md`
- `competitor` — from researcher's competitor matrix
- `defect` — from `--defects` pass (board: always on)

### Evidence

- For PRD/spec gaps: `path/to/file:line` of the missing or broken code.
- For checklist gaps: which PC code, file path, and one-line reason.
- For competitor claims: URL plus the date observed.

### Verdict (after review)

- `confirmed` — gap is real, action applies
- `exists after N+1` — was added in another spec, no action needed
- `duplicate of NNN` — already covered
- `drop` — false gap, do nothing

### Action

- `append tasks to spec NNN` — open spec gap, extend its tasks.md
- `new spec` — fresh feature, run `/kb-spec pre/plan/tasks`
- `fix spec` — defect cluster, `specs/NNN-fix-<area>/`
- `report only` — for `--report-only` customer projects, or non-blocking gaps

## Existing-Feature Verification on Main

A read-only table showing what the inventory + research found **already
exists** in code, with `path:line` cites. Establishes coverage; does not
claim tests passed. Example from Lumio:

| Feature checked | Verdict and evidence opened on main                | Action |
|-----------------|---------------------------------------------------|--------|
| Polling         | Exists: `backend/app/modules/sessions/polls.py:…` | No new spec |
| Class discussion| Partial: short-answer polling exists, no moderation | Spec 033 covers only moderation wall |

## Overlaps and Resolution

A bullet list of "spec X overlaps with spec Y — split as follows". Important
when several specs touch the same surface (auth, content, realtime).

## Spec Updates Proposed (skipped for `--report-only`)

Numbered list of all new specs and appended tasks this run will create.
Each entry: spec id, one-line description, source findings it addresses.

## Defect Clusters (only when `--defects`)

For each cluster:

- cluster id (e.g., `DEF-1`)
- summary
- evidence sources (failed tests, TODO counts, unresolved review findings)
- proposed spec: `specs/NNN-fix-<area>/`

These are listed **first** in the Phase 5 summary so they get owner
attention before new features.

## Owner Approval Checklist (Phase 5)

```
[ ] I have read the G codes and severities.
[ ] I approve the spec updates listed above.
[ ] I have NOT approved any implementation yet (Phase 6 needs explicit yes).
[ ] For customer projects, I confirm --report-only: no edits to specs/.
```

After owner ticks these, Phase 6 (kb-dev per spec) can start.