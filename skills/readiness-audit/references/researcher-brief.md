You are the implementer in <WORKTREE> (branch <BRANCH>). No skills, no MCP tools, no sub-agents. Never commit on main. No infra restarts, no emulators.

GOAL: Write `specs/_audit/<date>/research.md` for project <PROJECT_NAME>. Evidence-backed, no opinions. Own your work.

FILES IN SCOPE (read only these; open other files only if a test proves you must):
- `skills/readiness-audit/scripts/inventory.sh` — for the JSON facts you are explaining
- `skills/readiness-audit/references/prod-checklist.md` — the PC codes
- `skills/readiness-audit/references/gap-report-template.md` — output shape
- `scripts/gate/brief-template.md` — the worker contract you are running under
- <PROJECT_NAME>'s `PRD/` (or `docs/prd*`, or `*requirements*.md` — see inventory.json `prd`)
- <PROJECT_NAME>'s `specs/` (only the ones present; do not invent)

DO NOT TOUCH: <paths owned by other running jobs>; specifically `skills/kb-dev/`, `~/.specify/templates/`.

ACCEPTANCE (write these tests first, they must fail before the fix):
- N/A — research is a writing task. The artefact is the report itself.

LIMITS: research.md body <=150 words of summary at the top; the rest is
detailed evidence. WebSearch / WebRead only to confirm competitor URLs.
Cite `path:line` for every PRD/spec gap; cite PC code for every checklist gap.
If a gap is unprovable, drop it — do not include weak gaps. Maximum one pass.

LOCAL ENV: <PROJECT_NAME> repo path; `jq` is available; no servers.

Sections (a)-(d) are mandatory when their flag is on:
  (a) PRD/spec promises vs code — for each PRD bullet or spec claim, grep
      the repo and cite `file:line` where it exists or is missing.
  (b) Checklist pass/fail per PC code — walk every PC-* item, mark pass/fail
      with one-line evidence.
  (c) Competitor feature matrix — 3-5 competitors, columns: feature,
    our coverage, their coverage, URL.
  (d) Defects (only when `--defects`) — failing/skipped tests, TODO/FIXME
      stubs (`inventory.signals.stubs`), open tasks in done specs, unresolved
      review findings in `ai-knowledge-base/raw/` and PR threads, inbox bug
      reports. Each confirmed defect cluster gets a cluster id `DEF-n` and
      a proposed spec id `NNN-fix-<area>`.

REPORT (<=150 words): commit SHA (none — you do not commit), research.md
path, count of gaps by source (PRD/checklist/competitor/defect), top P0/P1
codes, anything you could not prove.