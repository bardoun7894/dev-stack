---
name: readiness-audit
description: "Run a per-project production-readiness audit (inventory -> research -> adversarial review -> spec updates -> STOP for owner approval -> implement -> verdict). Triggers on \"is X ready for production\", \"what's missing in X\", \"audit project X\", \"/readiness-audit <project>\", and Arabic \"شو ناقص بالمشروع\", \"جاهز للإنتاج\". Flags --report-only (customer projects: no spec/plan edits, report only) and --defects (defects pass: failing/skipped tests, open tasks in specs marked done in roadmap, TODO/FIXME/NotImplemented stubs, unresolved review findings, inbox bug reports). Phase 5 is a hard stop. Phase 6 uses kb-dev flow with researcher + reviewer."
allowed-tools: Bash Read Glob Grep Skill
---

# readiness-audit — production-readiness pipeline

A reusable per-project audit. Lives in `dev-stack` so any owner project can be
audited on demand. Phase 5 is a hard stop: nothing is implemented before the
owner says yes.

## Triggers

- `is X ready for production`
- `what's missing in X`
- `audit project X`
- `/readiness-audit <project>`
- Arabic: `شو ناقص بالمشروع`, `جاهز للإنتاج`

## Flags

- `--report-only` — customer projects (sanad_app and up): produce the report
  but do **not** edit `specs/` or `plan.md`. Report goes to the owner only.
- `--defects` — adds a defects pass to Phase 2 (board has it on by default):
  failing/skipped tests, open `- [ ]` tasks in specs that roadmap.md marks as
  done, TODO/FIXME/NotImplemented stubs, unresolved review findings in
  `ai-knowledge-base/raw/` and PR threads, inbox bug reports. Each confirmed
  defect cluster becomes its own `specs/NNN-fix-<area>/` spec, listed first
  at the Phase 5 stop.

## 8-phase table

| # | Phase                                | Who                                | Output                                             |
|---|--------------------------------------|------------------------------------|----------------------------------------------------|
| 0 | Locate + KB query                    | orchestrator                       | server or local path, KB [[wikilinks]]             |
| 1 | Inventory                            | `inventory.sh` (no AI, JSON)       | `specs/_audit/<date>/inventory.json`               |
| 2 | Research (incl. optional defects)    | `researcher` worker (sonnet)       | `specs/_audit/<date>/research.md`                  |
| 3 | Adversarial review                   | `reviewer` worker (different model)| trimmed gap list, G1..Gn, severities              |
| 4 | Spec updates (skipped for `--report-only`) | `planner` worker             | appended tasks, new specs, missing plan/tasks.md  |
| 5 | **STOP — owner approval**            | orchestrator                       | `READINESS-AUDIT-<date>.md` summary; nothing impl   |
| 6 | Implement approved specs             | kb-dev per spec                    | branches/PRs, tasks ticked                        |
| 7 | Verdict                              | re-run `inventory.sh` + checklist  | READY / NOT READY with remaining G codes           |

Phase 2 research brief (`references/researcher-brief.md`) covers (a) PRD/spec
promises vs code with grep evidence, (b) checklist pass/fail per PC code, (c)
3-5 competitors with feature matrix and URLs, plus (d) defects when `--defects`.

Phase 3 reviewer brief (`references/reviewer-brief.md`) is adversarial: verify
each G exists in code (cite `file:line`) or duplicates an existing spec, drop
false gaps. After writing `gap-report.md`, run `scripts/gaps-json.sh <gap-report.md> specs/_audit/<date>/gaps.json` (also in `--report-only`; `[]` when no gaps).

## Token budget

- one pass per worker
- at most 3 workers in parallel, only for different projects
- one review + one fix round
- gates run in bash, no polling

## Dispatch

```bash
jdelegate --no-auto-mcp --no-auto-skill --no-auto-role \
  --role researcher  "<project research brief>"
jdelegate --no-auto-mcp --no-auto-skill --no-auto-role \
  --role reviewer    "<project review brief>"
jdelegate --no-auto-mcp --no-auto-skill --no-auto-role \
  --role planner     "<project spec-update brief>"
```

## Where to run

Website projects run on **MyContabo** per `where-to-work`. Local projects run
on the developer's machine. The orchestrator picks based on the project's
own `where-to-work` config or `~/.claude/where-to-work.yaml`.

## References

- `references/prod-checklist.md` — coded items `PC-SEC-*`, `PC-OPS-*`,
  `PC-DATA-*`, `PC-UX-*`, `PC-I18N-*`, `PC-LEGAL-*`, `PC-TEST-*`. Deeper
  sources: parked `cso` (security), `harden` (errors/edge cases), `audit`
  (a11y/perf).
- `references/gap-report-template.md` — Lumio-style findings G1..Gn with
  source, severity, evidence, verdict, action.
- `references/researcher-brief.md`, `references/reviewer-brief.md` — briefs
  following `scripts/gate/brief-template.md`. Reports <=150 words; full
  output goes to a file.

## Scripts

- `scripts/inventory.sh <repo>` — emits JSON to stdout, no AI. <30s on a
  large repo. See `tests/readiness-audit/inventory_test.sh`.
- `scripts/gaps-json.sh <gap-report.md> <out.json>` — G-code table to
  `[{code,text,severity,source?}]`. See `tests/readiness-audit/gaps_json_test.sh`.