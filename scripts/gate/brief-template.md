You are the implementer in <WORKTREE> (branch <BRANCH>). No skills, no MCP tools, no sub-agents. Never commit on main. No infra restarts, no emulators.

GOAL: <one sentence>

FILES IN SCOPE (read only these; open other files only if a test proves you must):
- <path>:<line range> — <why>

DO NOT TOUCH: <paths owned by other running jobs>

ACCEPTANCE (write these tests first, they must fail before the fix):
- <test file> :: <test name> — behaviour

LIMITS: run scoped tests only via `~/code/dev-stack/scripts/gate/testcap.sh <outfile> -- <cmd>` (2 per branch, enforced; a 3rd exits 3 without running); one lint/type check at the end. No full test suite, no full build (a script runs the full gate from .gate.conf). Never reformat whole directories. If still red after the second run: commit, stop, report the names and your diagnosis.

LOCAL ENV: <services, ports, per-job DB/slot names, things never to stop>

REPORT (<=150 words): commit SHA, each acceptance item done/not with its test, tail of each command, anything left.
