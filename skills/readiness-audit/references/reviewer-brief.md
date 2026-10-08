You are the implementer in <WORKTREE> (branch <BRANCH>). No skills, no MCP tools, no sub-agents. Never commit on main. No infra restarts, no emulators.

GOAL: Adversarial review of the researcher's `specs/_audit/<date>/research.md`
for project <PROJECT_NAME>. Drop every gap that is not a real, actionable
missing thing. Be ruthless. Own your work.

FILES IN SCOPE (read only these; open other files only if a test proves you must):
- `specs/_audit/<date>/research.md` — the researcher's draft (mandatory input)
- `specs/_audit/<date>/inventory.json` — the deterministic facts
- `skills/readiness-audit/references/prod-checklist.md` — the PC codes
- <PROJECT_NAME>'s `specs/` — for the "duplicate of existing spec" check

DO NOT TOUCH: <paths owned by other running jobs>; specifically `skills/kb-dev/`, `~/.specify/templates/`.

ACCEPTANCE (write these tests first, they must fail before the fix):
- N/A — review is a writing task.

LIMITS: review report body <=150 words at the top; the rest is the
per-finding verdict table. Maximum one pass. You must not invent
requirements the researcher did not raise — your job is to delete, not
to add. If the researcher missed something, leave it for the next audit.

LOCAL ENV: <PROJECT_NAME> repo path; `jq` is available; no servers.

For each G code from the researcher's draft, you emit one row:

| G code | Decision | Reason |
|--------|----------|--------|
| G1 | drop / exists / duplicate / keep | `path:line` where it exists, or existing spec id |

Decisions:
  - `exists`     — code already implements it; cite `file:line`
  - `duplicate`  — covered by an existing spec; cite spec id
  - `keep`       — real gap, action applies
  - `drop`       — false gap, not a gap at all (e.g., misread PRD)

Severity and source come from the researcher; you do not re-rate unless
the gap is downgraded to P3 by the verdict.

REPORT (<=150 words): commit SHA (none), review report path, counts of
dropped vs kept, top surviving P0/P1 codes, anything you could not prove.