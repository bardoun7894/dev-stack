#!/bin/bash
# bash tests/test_spec_done.sh — scripts/gate/spec-done.sh (G12 + G17)
S="$(cd "$(dirname "$0")/.." && pwd)/scripts/gate/spec-done.sh"
T=$(mktemp -d); fails=0
mk() { mkdir -p "$T/$1/specs/001-x"; printf '%b' "$2" > "$T/$1/specs/001-x/tasks.md"; printf '%b' "$3" > "$T/$1/specs/001-x/spec.md"; }
MATRIX='## Done when\n\n| Flow | Expected |\n|---|---|\n| login | ok |\n'
check() { "$S" "$T/$1" specs/001-x >"$T/out" 2>&1; rc=$?; [ "$rc" = "$2" ] && grep -q "$3" "$T/out" && echo "ok   $1" || { echo "FAIL $1 (rc=$rc)"; cat "$T/out"; fails=1; }; }
mk clean   '- [x] T1 abc123\n- [x] T2 def456\n' "$MATRIX"
mk unchecked '- [x] T1\n- [ ] T2 todo\n' "$MATRIX"
mk nomatrix '- [x] T1\n' '## Done when\n\nIt works.\n'
mk matrix-in-tasks '- [x] T1\n\n## Done when\n\n| a | b |\n|---|---|\n| 1 | 2 |\n' 'no matrix here\n'
mk sibling-end '- [x] T1\n' '## Done when\n\n### Flows\n\n| a | b |\n|---|---|\n| 1 | 2 |\n'
mk higher-end '- [x] T1\n' '## Done when\n\n# Other\n\n| a | b |\n|---|---|\n| 1 | 2 |\n'
mk header-only '- [x] T1\n' '## Done when\n\n| a | b |\n|---|---|\n'
mk no-sep '- [x] T1\n' '## Done when\n\n| a | b |\n| 1 | 2 |\n'
check clean 0 "OK spec-done"
check unchecked 1 "T2 todo"
check nomatrix 1 "Done when"
check matrix-in-tasks 0 "OK spec-done"
check sibling-end 0 "OK spec-done"
check higher-end 1 "Done when"
check header-only 1 "Done when"
check no-sep 1 "Done when"
rm -rf "$T"; exit $fails
