#!/bin/bash
# spec-done.sh <repo> <specs/NNN-dir>  (G12 + G17, Phase 11 gate)
# Exit 1 with a list when tasks.md has unchecked "- [ ]" boxes, or when neither spec.md nor tasks.md has a
# "Done when" heading followed by a markdown table (the user-flow matrix).
set -u
[ $# -eq 2 ] || { echo "usage: spec-done.sh <repo> <specs/NNN-dir>" >&2; exit 2; }
dir="$1/$2"
[ -d "$dir" ] || { echo "spec-done: no such spec dir: $dir" >&2; exit 2; }
fail=0
tasks="$dir/tasks.md"
if [ -f "$tasks" ]; then
  open=$(grep -nE '^[[:space:]]*[-*] \[ \]' "$tasks")
  if [ -n "$open" ]; then
    echo "FAIL: unchecked tasks in $2/tasks.md (mark done only in the spec, with the SHA):"
    echo "$open" | sed 's/^/  line /'
    fail=1
  fi
else
  echo "FAIL: $2/tasks.md is missing"; fail=1
fi
has_matrix() {
  # the section ends at a heading of the same or higher level; need header row + separator row + >=1 data row
  awk '/^#+[[:space:]]/ {
      match($0, /^#+/); lvl = RLENGTH
      if (inh && lvl <= hl) inh = 0
      if (!inh && tolower($0) ~ /done when/) { inh = 1; hl = lvl; st = 0 }
      next }
    !inh { next }
    /^[[:space:]]*\|.*\|[[:space:]]*$/ {
      if (st == 0) st = 1
      else if (st == 1 && $0 ~ /^[[:space:]]*\|[[:space:]:|-]*-[[:space:]:|-]*\|[[:space:]]*$/) st = 2
      else if (st == 2) ok = 1
      next }
    { if (st != 2) st = 0 }
    END{exit ok?0:1}' "$1" 2>/dev/null
}
ok=0
for f in "$dir/spec.md" "$tasks"; do [ -f "$f" ] && has_matrix "$f" && ok=1; done
if [ $ok -eq 0 ]; then
  echo "FAIL: $2 has no 'Done when' heading followed by a markdown table (user-flow matrix) in spec.md or tasks.md"
  fail=1
fi
[ $fail -eq 0 ] && echo "OK spec-done: $2 (all tasks checked, Done-when matrix present)"
exit $fail
