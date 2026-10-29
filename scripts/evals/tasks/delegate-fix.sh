#!/bin/bash
# slow: a real jdelegate worker fixes a failing unittest in a scratch git repo.
here="$(cd "$(dirname "$0")" && pwd)"
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
cp "$here/../fixtures/buggy-calc/"* "$tmp/"
git -C "$tmp" init -q && git -C "$tmp" add -A && git -C "$tmp" -c user.email=e@e -c user.name=eval commit -qm init
before="$(grep -n 'range(' "$tmp/calc.py")"
out="$(jdelegate --no-auto-role --no-tab --timeout 15 --cwd "$tmp" "Fix the failing test in this repo (python3 -m unittest). Fix the bug in calc.py, then commit." 2>&1 </dev/null)"; rc=$?
if [ "$rc" != 0 ] && printf '%s' "$out" | grep -q "live workers already"; then echo "skipped: live-worker cap"; exit 2; fi
after="$(grep -n 'range(' "$tmp/calc.py")"
[ "$before" != "$after" ] || { echo "bug line unchanged (jdelegate rc=$rc)"; exit 1; }
(cd "$tmp" && python3 -m unittest -q >/dev/null 2>&1) || { echo "test still failing"; exit 1; }
echo "test passes, line now: $after"
