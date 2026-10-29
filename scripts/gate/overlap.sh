#!/bin/bash
# overlap.sh <repo-root> <branch...>: files changed vs main that 2+ given branches share. Zero AI.
R=${1:?usage: overlap.sh <repo-root> <branches...>}; shift; cd "$R" || exit 2
for b in "$@"; do git diff --name-only main..."$b" 2>/dev/null | sed "s|^|$b |"; done | awk '{c[$2]++; who[$2]=who[$2]" "$1} END{for(f in c) if(c[f]>1) print f":"who[f]}' | sort
