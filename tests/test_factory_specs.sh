#!/bin/bash
# bash tests/test_factory_specs.sh: skills/factory-issues/scripts/specs.py lists a project's specs from a git ref
# (never the working tree), shows done/total tasks and the merged stamp, and prints one spec with its open tasks.
PY="$(cd "$(dirname "$0")/.." && pwd)/skills/factory-issues/scripts/specs.py"
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
fail=0
bad() { echo "FAIL $1"; fail=1; }
R="$T/repo"; mkdir -p "$R/specs/001-login" "$R/specs/002-billing" "$R/specs/_session"
cd "$R" || exit 1
git init -q -b main . && git config user.email t@t && git config user.name t
printf '# Spec 001 — Login page\n\n**PR**: [#4](https://x/pull/4) — MERGED\n' > specs/001-login/spec.md
printf -- '- [x] T1 form\n- [ ] T2 hashing\n' > specs/001-login/tasks.md
printf '# Spec 002 — Billing\n' > specs/002-billing/spec.md
printf -- '- [x] T1 a\n- [x] T2 b\n' > specs/002-billing/tasks.md
echo x > specs/_session/log.md
git add -A && git commit -qm base
# working-tree edits must not show
printf -- '- [x] T1 form\n- [x] T2 hashing\n' > specs/001-login/tasks.md
mkdir -p specs/003-draft && echo '# Draft' > specs/003-draft/spec.md
P="$T/projects.json"
printf '[{"name":"demo","path":"%s","remote":"origin","main":"main","preview_watch_branch":"main"}]' "$R" > "$P"

out=$(FACTORY_PROJECTS="$P" python3 "$PY" demo 2>&1) || bad "list exit: $out"
echo "$out" | grep -q "001.*Login page.*1/2.*merged" || bad "001 row: $out"
echo "$out" | grep -q "002.*Billing.*2/2" || bad "002 row: $out"
echo "$out" | grep -q "003" && bad "working-tree spec leaked: $out"
echo "$out" | grep -q "_session" && bad "_session listed: $out"

one=$(FACTORY_PROJECTS="$P" python3 "$PY" demo 001 2>&1) || bad "one exit: $one"
echo "$one" | grep -q "Spec 001" || bad "one title: $one"
echo "$one" | grep -q "T2 hashing" || bad "open task missing: $one"
echo "$one" | grep -q "\[x\] T1 form" && bad "done task shown as open: $one"

all=$(FACTORY_PROJECTS="$P" python3 "$PY" 2>&1) || bad "projects exit: $all"
echo "$all" | grep -q "demo.*2 specs" || bad "projects row: $all"

js=$(FACTORY_PROJECTS="$P" python3 "$PY" demo --json 2>&1) || bad "json exit"
echo "$js" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d[0]["nnn"]=="001" and d[0]["done"]==1 and d[0]["total"]==2 and d[0]["merged"]' || bad "json: $js"

FACTORY_PROJECTS="$P" python3 "$PY" nope >/dev/null 2>&1 && bad "unknown project should fail"
[ $fail = 0 ] && echo "ok factory specs"
exit $fail
