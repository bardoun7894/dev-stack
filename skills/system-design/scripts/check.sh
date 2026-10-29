#!/usr/bin/env bash
# Zero-AI gate for specs/NNN/system-design.md
# Usage: check.sh <file> --lite|--full   (exit 0 pass, 1 fail, 2 usage)
set -u

file="${1:-}"
mode="${2:-}"
if [ -z "$file" ] || { [ "$mode" != "--lite" ] && [ "$mode" != "--full" ]; }; then
  echo "usage: check.sh <system-design.md> --lite|--full" >&2
  exit 2
fi
if [ ! -f "$file" ]; then
  echo "FAIL: file not found: $file" >&2
  exit 1
fi

if [ "$mode" = "--lite" ]; then
  sections="1 2 4 6 9 10"
else
  sections="1 2 3 4 5 6 7 8 9 10"
fi

missing=""
for n in $sections; do
  grep -Eq "^##[[:space:]]+${n}\.[[:space:]]" "$file" || missing="${missing}missing heading: ## ${n}.\n"
done
grep -Eq '^```mermaid' "$file" || missing="${missing}missing: at least one \`\`\`mermaid block\n"
grep -Eq '(^|[^A-Za-z0-9])D1([^0-9]|$)' "$file" || missing="${missing}missing: decision D1\n"
bad=$(grep -nEi '\b(TBD|TODO|lorem)\b' "$file" | head -5)
[ -z "$bad" ] || missing="${missing}placeholder text found:\n${bad}\n"

# template placeholders (outside mermaid blocks and HTML comments)
ph=$(awk '
  /^```mermaid/ { m=1; next }
  m && /^```/ { m=0; next }
  m { next }
  {
    line=$0
    if (c) { if (sub(/^.*-->/, "", line)) c=0; else next }
    while (match(line, /<!--/)) {
      pre=substr(line, 1, RSTART-1); rest=substr(line, RSTART+4)
      if (match(rest, /-->/)) line=pre substr(rest, RSTART+3)
      else { line=pre; c=1; break }
    }
    if (line ~ /<[A-Za-z|_ -]+>/ || line ~ /YYYY-MM-DD/ || line ~ /NNN-/) printf "%d:%s\n", NR, $0
  }' "$file" | head -10)
[ -z "$ph" ] || missing="${missing}template placeholders still present:\n${ph}\n"

if [ -n "$missing" ]; then
  echo "FAIL ($mode): $file"
  printf '%b' "$missing"
  exit 1
fi
echo "PASS ($mode): $file"
exit 0
