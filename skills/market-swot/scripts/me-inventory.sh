#!/usr/bin/env bash
# skills/market-swot/scripts/me-inventory.sh
# Zero-AI inventory of the owner's public/personal-brand footprint. JSON to stdout.
set -u
command -v jq >/dev/null || { echo "jq required" >&2; exit 1; }
PORTFOLIO_DIR="${PORTFOLIO_DIR:-$HOME/projects/portfolio-next}"
PROJECTS_DIR="${PROJECTS_DIR:-$HOME/projects}"
MEMORY_INDEX="${MEMORY_INDEX:-$HOME/.claude/projects/-Users-mohamedbardouni-projects/memory/MEMORY.md}"
lines() { awk 'NF' | jq -R . | jq -s .; }

# portfolio
pexists=false; pfiles='[]'
if [ -d "$PORTFOLIO_DIR" ]; then
  pexists=true
  pfiles="$(cd "$PORTFOLIO_DIR" && find . -maxdepth 4 \( -name node_modules -o -name .git -o -name .next \) -prune -o -type f \
    \( -name '*.md' -o -name '*.mdx' -o -name '*.json' \) -path '*content*' -print 2>/dev/null | sed 's|^\./||' | sort | head -200 | lines)"
fi

# github
gh_json='{"gh_available":false,"repos":[]}'
if command -v gh >/dev/null 2>&1; then
  repos="$(gh repo list --limit 100 --json name,description,stargazerCount,updatedAt 2>/dev/null)"
  if [ $? -eq 0 ] && echo "$repos" | jq -e 'type=="array"' >/dev/null 2>&1; then
    gh_json="$(jq -n --argjson r "$repos" '{gh_available:true,repos:$r}')"
  fi
fi

# projects top-level dirs
projects='[]'
[ -d "$PROJECTS_DIR" ] && projects="$(find "$PROJECTS_DIR" -mindepth 1 -maxdepth 1 -type d ! -name '.*' -exec basename {} \; 2>/dev/null | sort | lines)"

# memory index
mem='{"count":0,"titles":[]}'
if [ -f "$MEMORY_INDEX" ]; then
  titles="$(grep -E '^- \[' "$MEMORY_INDEX" | sed -E 's/^- \[([^]]*)\].*/\1/' | lines)"
  mem="$(jq -n --argjson t "$titles" '{count:($t|length),titles:$t}')"
fi

jq -n --arg dir "$PORTFOLIO_DIR" --argjson exists "$pexists" --argjson files "$pfiles" \
  --argjson gh "$gh_json" --argjson projects "$projects" --argjson mem "$mem" \
  '{portfolio:{dir:$dir,exists:$exists,content_files:$files},github:$gh,projects:$projects,memory:$mem}'
