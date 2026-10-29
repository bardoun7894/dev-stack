#!/bin/bash
# bash tests/test_gate_run_guard.sh — hooks/gate-run-guard.sh (G5/G6): heavy commands must be wrapped in gate-run
H="$(cd "$(dirname "$0")/.." && pwd)/hooks/gate-run-guard.sh"
fails=0
# check <name> <expected-rc> <os> <command>
check() {
  local out rc
  out=$(jq -n --arg c "$4" '{tool_input:{command:$c}}' | GATE_GUARD_UNAME="$3" "$H" 2>&1 >/dev/null); rc=$?
  if [ "$rc" = "$2" ] && { [ "$2" = 0 ] || printf '%s' "$out" | grep -q 'gate-run'; }; then echo "ok   $1"; else echo "FAIL $1 (rc=$rc, want $2) $out"; fails=1; fi
}
check mac-ssh-wrapped 0 Darwin 'ssh MyContabo "cd /root/x && gate-run x 45m -- pnpm build"'
check mac-ssh-bare 2 Darwin 'ssh MyContabo "cd /root/x && pnpm build"'
check mac-local-build 0 Darwin 'pnpm build'
check mac-ssh-light 0 Darwin 'ssh MyContabo "cd /root/x && git status"'
check mac-ssh-playwright 2 Darwin 'ssh MyContabo "cd /root/x && playwright test"'
check mac-ssh-ops-test 2 Darwin 'ssh MyContabo "cd /root/x && ops/test.sh"'
check mac-ssh-skip 0 Darwin 'GATE_SKIP=1 ssh MyContabo "cd /root/x && pnpm build"'
check mac-ssh-pest-bare 2 Darwin 'ssh MyContabo "cd /root/x && vendor/bin/pest"'
check mac-ssh-pest-filter 0 Darwin 'ssh MyContabo "cd /root/x && vendor/bin/pest --filter Foo"'
check mac-ssh-vitest-bare 2 Darwin 'ssh MyContabo "cd /root/x && vitest run"'
check mac-ssh-vitest-file 0 Darwin 'ssh MyContabo "cd /root/x && vitest run src/a.test.ts"'
check mac-ssh-pytest-bare 2 Darwin 'ssh MyContabo "cd /root/x && pytest -q"'
check mac-ssh-pytest-path 0 Darwin 'ssh MyContabo "cd /root/x && pytest tests/test_a.py"'
check mac-commit-text 0 Darwin 'git commit -m "docs: ssh MyContabo pnpm build needs gate-run"'
check srv-build 2 Linux 'cd /root/x && pnpm build'
check srv-npm-build 2 Linux 'npm run build'
check srv-next-build 2 Linux 'next build'
check srv-wrapped 0 Linux 'cd /root/x && gate-run x 45m -- pnpm build'
check srv-skip 0 Linux 'GATE_SKIP=1 pnpm build'
check srv-echo-text 0 Linux 'echo "run pnpm build later"'
check srv-commit-text 0 Linux 'git commit -m "fix: pnpm build script"'
check srv-heredoc 0 Linux $'cat > notes.md <<EOF\npnpm build\nEOF'
check srv-light 0 Linux 'ls -la'
check mac-ssh-npx-tsc 2 Darwin 'ssh MyContabo "cd /root/x && npx tsc --noEmit"'
check mac-ssh-npx-tsc-quoted 2 Darwin "ssh MyContabo 'cd /root/x && npx tsc --noEmit'"
check mac-ssh-tsc-wrapped 0 Darwin 'ssh MyContabo "cd /root/x && gate-run x 20m -- npx tsc --noEmit"'
check mac-ssh-tsc-files 0 Darwin 'ssh MyContabo "cd /root/x && npx tsc --noEmit src/a.ts src/b.ts"'
check mac-ssh-tsc-version 0 Darwin 'ssh MyContabo "cd /root/x && npx tsc --version"'
check srv-tsc 2 Linux 'tsc --noEmit'
check srv-tsc-project 2 Linux 'cd /root/x && tsc -p tsconfig.json --noEmit'
check srv-pnpm-tsc 2 Linux 'pnpm tsc --noEmit'
check srv-pnpm-exec-tsc 2 Linux 'pnpm exec tsc --noEmit'
check srv-npm-exec-tsc 2 Linux 'npm exec tsc -- --noEmit'
check srv-bin-tsc 2 Linux './node_modules/.bin/tsc --noEmit'
check srv-tsc-file 0 Linux 'npx tsc --noEmit src/a.ts'
check srv-tsc-wrapped 0 Linux 'gate-run x 20m -- npx tsc --noEmit'
check srv-tsconfig-text 0 Linux 'cat tsconfig.json'
check srv-tsc-alias 0 Linux 'npx tsc-alias'
check srv-commit-tsc-text 0 Linux 'git commit -m "ci: run tsc --noEmit"'
exit $fails
