# Feature Specification: readiness-audit

**Feature Branch**: `001-readiness-audit`  
**PR**: TBD  
**Merged**: TBD  
**Created**: 2026-10-08  
**Status**: Draft  
**Input**: Build a reusable per-project production-readiness audit skill.

## User Scenarios & Testing

### User Story 1 - Audit an own project end-to-end (Priority: P1)

Owner runs `/readiness-audit <project>` on an internal project. It produces
`specs/_audit/<date>/{inventory.json, research.md, gap-report.md}`, the
spec updates land in `specs/NNN-*/`, and the run stops at Phase 5 for the
owner's yes/no on each P0/P1.

**Why this priority**: this is the core value of the skill.

**Independent Test**: run on board; verify all four artefacts exist and the
Phase 5 stop file lists P0/P1 codes.

**Acceptance Scenarios**:

1. **Given** a project with PRD + specs, **When** owner runs the skill, **Then** inventory.json, research.md, gap-report.md are written and the run halts at Phase 5.
2. **Given** the run halted at Phase 5, **When** owner says yes, **Then** Phase 6 (kb-dev) starts per approved spec.

### User Story 2 - Audit a customer project without spec edits (Priority: P2)

Owner runs `/readiness-audit <customer-project> --report-only`. The skill
runs phases 1-3 and 7, writes the report only, and **does not** modify
`specs/`. `git status` after the run shows no changes under `specs/`.

**Why this priority**: customer data discipline — we audit but don't write.

**Independent Test**: run on sanad_app with `--report-only`; `git diff --stat`
shows no changes under `specs/`.

**Acceptance Scenarios**:

1. **Given** a customer project, **When** owner runs with `--report-only`, **Then** no files under `specs/` are created or modified.

### User Story 3 - Defects pass on board (Priority: P2)

For board (and any project run with `--defects`), Phase 2 includes a (d)
defects section: failing/skipped tests, open tasks in done specs, TODO/
FIXME/NotImplemented stubs, unresolved review findings, inbox bug reports.
Each confirmed defect cluster becomes `specs/NNN-fix-<area>/` and is
listed first in the Phase 5 stop file.

**Why this priority**: board was the original motivation for the skill.

**Independent Test**: run on board; verify at least one `specs/NNN-fix-*/`
directory is created when defects are found.

**Acceptance Scenarios**:

1. **Given** board has defects, **When** the audit runs, **Then** Phase 2(d) lists defect clusters and Phase 4 creates `specs/NNN-fix-<area>/` per cluster.

## Requirements

### Functional Requirements

- **FR-001**: The skill MUST emit deterministic JSON from `inventory.sh` with no AI in that step.
- **FR-002**: Phase 5 MUST be a hard stop — no Phase 6 work without an explicit owner yes.
- **FR-003**: The skill MUST honour `--report-only` for customer projects (no `specs/` edits).
- **FR-004**: The skill MUST support `--defects` for an audit-mode defects pass; board runs it by default.
- **FR-005**: Dispatch MUST use `jdelegate --no-auto-mcp --no-auto-skill --no-auto-role --role researcher|reviewer|planner`.

### Key Entities

- **inventory.json**: deterministic repo facts — git state, PRD paths, specs count, signals, stubs count.
- **research.md**: researcher's evidence-backed draft, sections (a)-(d) when applicable.
- **gap-report.md**: G codes with source/severity/evidence/verdict/action.
- **specs/NNN-fix-<area>/**: a defect cluster spec, created during Phase 4.

## Success Criteria

- **SC-001**: `inventory.sh` runs in <30s on a large repo (verified against the dev-stack and FashionVerse repos).
- **SC-002**: At least 60 PC codes are present in `prod-checklist.md`.
- **SC-003**: The fixture test `tests/readiness-audit/inventory_test.sh` passes.
- **SC-004**: Running with `--report-only` on a customer repo leaves `specs/` untouched.