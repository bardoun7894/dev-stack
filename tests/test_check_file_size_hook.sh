#!/bin/bash
# bash tests/test_check_file_size_hook.sh — size hook blocks new/crossing/grown>10% oversized files, lets small edits to already-big files pass
HOOK="$(cd "$(dirname "$0")/.." && pwd)/scripts/githooks/check-file-size"
T=$(mktemp -d); fails=0
cd "$T" && git init -q . && git config user.email t@t && git config user.name t; git config core.hooksPath /dev/null
gen() { head -c "$2" /dev/zero | tr '\0' 'a' | fold -w 80 > "$1"; echo >> "$1"; } # ~$2 bytes
gen big.txt 24000; gen small.txt 10000; gen edge.txt 18000
git add . && git commit -qm base
check() { # name expected-rc
  "$HOOK" >/dev/null 2>&1; rc=$?
  [ "$rc" = "$2" ] && echo "ok   $1" || { echo "FAIL $1 (rc=$rc, want $2)"; fails=1; }
  git reset -q --hard HEAD; git clean -qfd
}
echo "x" >> big.txt; git add -A; check already-big-small-edit 0
head -c 1000 /dev/zero | tr '\0' 'b' >> big.txt; git add -A; check already-big-grows-4pct 0
head -c 3000 /dev/zero | tr '\0' 'b' >> big.txt; git add -A; check already-big-grows-12pct 1
head -c 6000 /dev/zero | tr '\0' 'b' >> small.txt; head -c 6000 /dev/zero | tr '\0' 'b' >> small.txt; git add -A; check crosses-limit 1
head -c 800 /dev/zero | tr '\0' 'b' >> edge.txt; git add -A; check under-limit-after 0
head -c 2500 /dev/zero | tr '\0' 'b' >> edge.txt; git add -A; check crosses-limit-edge 1
gen newbig.txt 21000; git add -A; check new-file-over 1
gen newok.txt 5000; git add -A; check new-file-under 0
head -c 5000 /dev/zero | tr '\0' 'b' >> big.txt; git add -A; SKIP_TOKEN_CHECK=1 check skip-escape 0
git rm -q big.txt; check delete-big 0
gen big.txt 21000; git add -A; check shrink-big 0
cd /; rm -rf "$T"; exit $fails
