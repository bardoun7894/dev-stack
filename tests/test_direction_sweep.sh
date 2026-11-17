#!/bin/bash
# bash tests/test_direction_sweep.sh: skills/direction/scripts/sweep.py lists stale-context candidates and changes nothing
PY="$(cd "$(dirname "$0")/.." && pwd)/skills/direction/scripts/sweep.py"
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
fail=0
bad() { echo "FAIL $1"; fail=1; }
R="$T/repo"; M="$T/memory"; mkdir -p "$R/src" "$R/specs/001-x" "$M"
cd "$R" || exit 1
git init -q -b main . && git config user.email t@t && git config user.name t && git config core.hooksPath /dev/null
printf 'def a():\n    # TODO: retry later\n    return 1\n' > src/app.py
printf '# Project\nEntry point is `src/app.py`; old router in `src/router.py`; template `specs/NNN/tasks.md`.\n' > CLAUDE.md
printf -- '- [ ] T001 router\n- [x] T002 app (abc1234, 2026-11-01)\n- [ ] FU1 later\n' > specs/001-x/tasks.md
printf 'The handler lives in `src/handler.py`; the app is `src/app.py`.\n' > "$M/note.md"
git add -A && git commit -qm base
# the TODO line is made "old" by back-dating its commit
GIT_COMMITTER_DATE="2024-01-01T00:00:00" git commit -q --amend --no-edit --date "2024-01-01T00:00:00"
before=$(git status --porcelain; git rev-parse HEAD; ls -R "$M")

out=$(python3 "$PY" "$R" --memory "$M" --no-gh)
echo "$out" | grep -q 'DOC-PATH.*`src/router.py` does not exist' || bad "missing doc path not listed"
echo "$out" | grep -q 'src/app.py` does not exist' && bad "existing path listed as missing"
echo "$out" | grep -q 'specs/NNN/tasks.md` does not exist' && bad "placeholder path listed"
echo "$out" | grep -q 'MEMORY-PATH.*`src/handler.py`' || bad "memory path not listed"
echo "$out" | grep -q 'NOTE-OLD *src/app.py:2' || bad "old TODO not listed"
echo "$out" | grep -q 'SPEC-OPEN.*T001' || bad "open task before a merged one not listed"
echo "$out" | grep -q 'SPEC-OPEN.*FU1' && bad "follow-up listed as SPEC-OPEN"
after=$(git status --porcelain; git rev-parse HEAD; ls -R "$M")
[ "$before" = "$after" ] || bad "sweep changed the repo or memory"
python3 "$PY" "$T/nowhere-$$" --no-gh >/dev/null 2>&1; [ $? -eq 0 ] || bad "missing repo must not crash (report, not gate)"

[ $fail -eq 0 ] && echo "PASS test_direction_sweep" || exit 1
