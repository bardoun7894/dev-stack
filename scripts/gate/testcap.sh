#!/bin/bash
# testcap.sh <outfile> -- <test command...> | --reset | --status
# Caps scoped test runs per git worktree + branch (TESTCAP_MAX, default 2). Exit 3 = cap reached, command not run.
MAX=${TESTCAP_MAX:-2}
top=$(git rev-parse --show-toplevel 2>/dev/null) || { echo "testcap: not in a git worktree" >&2; exit 2; }
br=$(git branch --show-current 2>/dev/null); [ -n "$br" ] || br=$(git rev-parse --short HEAD)
dir=~/.cache/gate/testcap; mkdir -p "$dir"
cf="$dir/$(printf '%s@%s' "$top" "$br" | tr -c 'A-Za-z0-9._-\n' '_').count"
n=$(cat "$cf" 2>/dev/null); n=${n:-0}
case "$1" in
  --reset) echo 0 > "$cf"; echo "testcap: reset for $br (0/$MAX)"; exit 0;;
  --status) echo "$n/$MAX"; exit 0;;
esac
out=$1; shift
[ -n "$out" ] && [ "$1" = "--" ] && [ $# -gt 1 ] || { echo "usage: testcap.sh <outfile> -- <test command...> | --reset | --status" >&2; exit 2; }
shift
if [ "$n" -ge "$MAX" ]; then
  echo "testcap: $n/$MAX scoped runs used for $br; stop, commit, report names + diagnosis" >&2
  exit 3
fi
n=$((n+1)); echo "$n" > "$cf"
"$@" > "$out" 2>&1; rc=$?
tail -n 1 "$out"
echo "testcap: run $n/$MAX"
exit $rc
