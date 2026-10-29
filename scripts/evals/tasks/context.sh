#!/bin/bash
# Does a bare claude -p know who the owner is and what they sell?
cd /tmp || exit 1
ans="$(perl -e 'alarm shift; exec @ARGV' 180 claude -p "Who is the owner of this setup, and what products and clients do they have? Be specific." </dev/null 2>&1)" || { echo "claude failed: ${ans:0:120}"; exit 1; }
[ -n "$ans" ] || { echo "empty answer"; exit 1; }
p="$(printf '%s' "$ans" | jev noul "This answer names specific products such as Ornina Studio or MarktingTeam and specific clients" -q 2>&1)"; rc=$?
[ "$rc" = 0 ] || { echo "jev error rc=$rc: ${p:0:100}"; exit 1; }
echo "p=$p"
awk -v p="$p" 'BEGIN{exit !(p>=0.7)}'
