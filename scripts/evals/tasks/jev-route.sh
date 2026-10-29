#!/bin/bash
# A trivial edit must route to a cheap tier (T0 or T1).
r="$(jev route "rename a variable in one file" 2>&1)" || { echo "jev error: ${r:0:100}"; exit 1; }
tier="$(printf '%s' "$r" | jq -r .choice 2>/dev/null)"
echo "tier=$tier"
[ "$tier" = T0 ] || [ "$tier" = T1 ]
