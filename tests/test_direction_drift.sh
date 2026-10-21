#!/bin/bash
# bash tests/test_direction_drift.sh: skills/direction/scripts/drift.sh maps commits to specs, flags UNMAPPED, and marks non-negotiables HAS-CHECK / NO-CHECK
SH="$(cd "$(dirname "$0")/.." && pwd)/skills/direction/scripts/drift.sh"
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
fail=0
bad() { echo "FAIL $1"; fail=1; }
R="$T/repo"; mkdir -p "$R/specs/001-login-flow" "$R/specs/002-billing" "$R/tests"
cd "$R" || exit 1
git init -q -b main . && git config user.email t@t && git config user.name t
cat > CLAUDE.md <<'MD'
# Project
## Non-negotiable rules
- Passwords must be hashed with bcrypt before storage
- Invoices must never be deleted, only voided
MD
printf '# Feature Specification: Login flow\n' > specs/001-login-flow/spec.md
printf -- '- [x] T001 form\n- [ ] T002 hashing\n' > specs/001-login-flow/tasks.md
printf '# Feature Specification: Billing\n' > specs/002-billing/spec.md
printf -- '- [ ] T010 invoices\n- [ ] T011 ledger in `src/billing/invoice.ts`\n' > specs/002-billing/tasks.md
echo "assert passwords hashed with bcrypt before storage" > tests/auth.test.js
git add -A && git commit -qm "chore: base"
git checkout -q -b 001-login-flow
echo a > a.txt && git add -A && git commit -qm "feat: 001-login-flow form"
echo b > b.txt && git add -A && git commit -qm "feat: T010 invoice list"
echo n > specs/002-billing/notes.md && git add -A && git commit -qm "feat: tweak notes"
mkdir -p src/billing && echo l > src/billing/invoice.ts && git add -A && git commit -qm "feat: refactor ledger"
mkdir -p ai-knowledge-base && echo k > ai-knowledge-base/notes.md && git add -A && git commit -qm "docs(kb): sync notes"
git checkout -q main && git checkout -q -b scratch
echo c > c.txt && git add -A && git commit -qm "feat: random dark mode toggle"

out=$(bash "$SH" "$R" --since main 2>&1); rc=$?
[ $rc = 0 ] || bad "exit $rc"
case "$out" in *"| 001-login-flow | Feature Specification: Login flow | 1 | 1 |"*) ;; *) bad "spec table: $out";; esac
case "$out" in *"random dark mode toggle | UNMAPPED"*) ;; *) bad "unmapped not flagged";; esac
case "$out" in *"- commits: 1, mapped to a spec: 0, housekeeping: 0, UNMAPPED: 1"*) ;; *) bad "summary scratch";; esac
case "$out" in *"bcrypt before storage"*"HAS-CHECK"*"tests/auth.test.js"*) ;; *) bad "HAS-CHECK";; esac
case "$out" in *"never be deleted, only voided"*"NO-CHECK"*) ;; *) bad "NO-CHECK";; esac

git checkout -q 001-login-flow
out=$(bash "$SH" "$R" --since main 2>&1)
case "$out" in *"001-login-flow form | 001-login-flow (subject)"*) ;; *) bad "subject map: $out";; esac
case "$out" in *"T010 invoice list | 002-billing (T-number T010)"*) ;; *) bad "T-number map";; esac
case "$out" in *"| feat: tweak notes | 002-billing (spec-files) |"*) ;; *) bad "spec-files map: $out";; esac
case "$out" in *"| feat: refactor ledger | 002-billing (task-path) |"*) ;; *) bad "task-path map: $out";; esac
case "$out" in *"| docs(kb): sync notes | HOUSEKEEPING |"*) ;; *) bad "housekeeping row: $out";; esac
case "$out" in *"- commits: 5, mapped to a spec: 4, housekeeping: 1, UNMAPPED: 0"*) ;; *) bad "summary mapped: $out";; esac
case "$out" in *"- mechanical on-plan: 100%"*) ;; *) bad "on-plan denominator: $out";; esac

bash "$SH" /nonexistent >/dev/null 2>&1; [ $? = 2 ] || bad "bad repo should exit 2"
[ $fail = 0 ] && echo "PASS test_direction_drift"
exit $fail
