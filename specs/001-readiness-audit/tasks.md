# Tasks: readiness-audit

**Input**: Design documents from `/specs/001-readiness-audit/`
**Prerequisites**: plan.md, spec.md

## Phase 1: Setup

- [x] T001 Create `skills/readiness-audit/{scripts,references}` directories
- [x] T002 Create `specs/001-readiness-audit/` and `tests/readiness-audit/`
- [x] T003 Create `agents/researcher.md` (and mirror to `~/.claude/agents-parked/`)

## Phase 2: Inventory (P1)

- [x] T010 [P] Write `tests/readiness-audit/inventory_test.sh` fixture (TDD red)
- [x] T011 Implement `skills/readiness-audit/scripts/inventory.sh` (TDD green)
- [x] T012 [P] Verify on FashionVerse: `jq '.specs|length'` >= 14

## Phase 3: Skill docs (P1)

- [x] T020 Write `skills/readiness-audit/SKILL.md` with frontmatter + 8-phase table + flags
- [x] T021 [P] Write `references/prod-checklist.md` with PC-* codes (>=60 items)
- [x] T022 [P] Write `references/gap-report-template.md` modeled on Lumio
- [x] T023 [P] Write `references/researcher-brief.md` and `reviewer-brief.md`

## Phase 4: Spec docs (P1)

- [x] T030 [P] Write `specs/001-readiness-audit/spec.md`
- [x] T031 [P] Write `specs/001-readiness-audit/plan.md`
- [x] T032 [P] Write `specs/001-readiness-audit/tasks.md` (this file)

## Phase 5: Symlink + verification

- [x] T040 Symlink `~/.claude/skills/readiness-audit` -> `/Users/mohamedbardouni/code/dev-stack/skills/readiness-audit`
- [x] T041 Save full test outputs to `/tmp/readiness-a1-*.log`
- [x] T042 Commit on `readiness-audit` branch (no Co-Authored-By line)

## Dependencies

- T010 -> T011 (test-first)
- T011 -> T012 (verify on real repo)
- T011 + T020-T023 -> T030-T032 (skill exists before its own spec)
- T040-T042 last

## Verification

- `bash tests/readiness-audit/inventory_test.sh` exits 0
- `bash skills/readiness-audit/scripts/inventory.sh /Users/mohamedbardouni/projects/FashionVerse | jq '.specs|length'` >= 14
- No files outside the listed paths touched