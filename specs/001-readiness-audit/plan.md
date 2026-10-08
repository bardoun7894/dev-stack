# Implementation Plan: readiness-audit

**Branch**: `001-readiness-audit` | **Date**: 2026-10-08 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/001-readiness-audit/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/commands/plan.md` for the execution workflow.

## Research (Phase 2a)

This skill **is** a research-driven pipeline, so `research.md` lives one
level down at `specs/_audit/<date>/research.md` per project. Skill
references:

- `references/prod-checklist.md` — 78 PC codes across 9 categories, with
  applicability columns.
- `references/gap-report-template.md` — Lumio-style G codes.
- `references/researcher-brief.md`, `references/reviewer-brief.md` — worker
  contracts.

External sources are the parked `cso`/`harden`/`audit` skills, used as
deeper rubrics rather than re-authored content.

## Summary

Build a reusable per-project production-readiness audit. The skill lives in
`dev-stack` (this repo) and is symlinked into `~/.claude/skills/`. It runs
an 8-phase pipeline (inventory -> research -> review -> spec updates ->
STOP -> implement -> verdict) with hard token-budget rules and an owner
approval gate before any code is touched.

## Technical Context

**Language/Version**: bash 3.2+ (script) + Markdown (docs)  
**Primary Dependencies**: `jq`, `git`, `grep`, `find`. No language runtime.  
**Storage**: N/A (script reads only)  
**Testing**: bash fixture test (`tests/readiness-audit/inventory_test.sh`)  
**Target Platform**: macOS + Linux, where `jq` and `git` are on PATH  
**Project Type**: single repo, skill assets + scripts  
**Performance Goals**: `inventory.sh` <30s on large repos (verified: 0.8s on FashionVerse)  
**Constraints**: must finish in one pass per worker; max 3 parallel  
**Scale/Scope**: ~60-90 checklist items, 4 reference docs, 1 script, 1 test, 1 agent file

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- TDD: `inventory_test.sh` written first, run red, then `inventory.sh` written to green. PASS.
- Token budget: documented in SKILL.md and the briefs. PASS.
- Owner stop: Phase 5 explicit in SKILL.md and gap-report-template.md. PASS.

## Project Structure

### Documentation (this feature)

```text
specs/001-readiness-audit/
├── spec.md              # this spec
├── plan.md              # this plan
└── tasks.md             # phase-by-phase task breakdown
```

### Source Code

```text
skills/readiness-audit/
├── SKILL.md                                # skill entry, frontmatter + phase table
├── scripts/
│   └── inventory.sh                        # deterministic JSON, no AI
├── references/
│   ├── prod-checklist.md                   # 78 PC codes
│   ├── gap-report-template.md              # Lumio-shaped G codes
│   ├── researcher-brief.md                 # worker contract for Phase 2
│   └── reviewer-brief.md                   # worker contract for Phase 3
└── tests/                                  # (test lives at repo root)

agents/researcher.md                        # new agent (sonnet, read-only)
~/.claude/agents-parked/researcher.md       # mirror

tests/readiness-audit/
└── inventory_test.sh                       # fixture test, runs in bash
```

## Complexity Tracking

No constitution violations. Single-language (bash + Markdown) project;
no parallel stacks to manage.