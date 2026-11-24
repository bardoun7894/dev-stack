#!/usr/bin/env bash
# Zero-AI gate for specs/NNN/ux-architecture.md
# Usage: check.sh <file> --lite|--full   (exit 0 pass, 1 fail, 2 usage)
set -u

file="${1:-}"
mode="${2:-}"
if [ -z "$file" ] || { [ "$mode" != "--lite" ] && [ "$mode" != "--full" ]; }; then
  echo "usage: check.sh <ux-architecture.md> --lite|--full" >&2
  exit 2
fi
if [ ! -f "$file" ]; then
  echo "FAIL: file not found: $file" >&2
  exit 1
fi

if [ "$mode" = "--lite" ]; then
  sections="1 2 3 4 5 6 8"
else
  sections="1 2 3 4 5 6 7 8"
fi

missing=""
for n in $sections; do
  grep -Eq "^##[[:space:]]+${n}\.[[:space:]]" "$file" || missing="${missing}missing heading: ## ${n}.\n"
done

# Required Semantic IxD, Posture, Flow, Latency, and Decision artifacts
grep -Eiq '\|[^|]*Object[^|]*\|[^|]*Action' "$file" || missing="${missing}missing: Object-Action-Attribute Matrix table\n"
grep -Eiq '\b(Sovereign|Transient|Daemonic)\b' "$file" || missing="${missing}missing: Application Posture (Sovereign/Transient/Daemonic)\n"
grep -Eq '^```mermaid' "$file" || missing="${missing}missing: at least one \`\`\`mermaid flow diagram\n"
grep -Eq '(^|[^A-Za-z0-9])UX-D1([^0-9]|$)' "$file" || missing="${missing}missing: UX decision UX-D1\n"
grep -Eiq '100[[:space:]]*ms|0\.1[[:space:]]*s' "$file" || missing="${missing}missing: 100ms responsiveness budget\n"
grep -Eiq '400[[:space:]]*ms|1[[:space:]]*s' "$file" || missing="${missing}missing: 400ms / 1s responsiveness budget\n"
grep -Eiq 'Trunk Test' "$file" || missing="${missing}missing: Krug Trunk Test validation routes\n"

# Reject placeholder words
bad=$(grep -nEi '\b(TBD|TODO|FIXME|lorem)\b' "$file" | head -5)
[ -z "$bad" ] || missing="${missing}placeholder text found:\n${bad}\n"

# Reject unfilled angle-bracket template placeholders outside fenced code blocks and HTML comments
ph=$(awk '
  /^```/ { f = !f; next }
  f { next }
  {
    line = $0
    if (c) {
      if (sub(/^.*-->/, "", line)) c = 0
      else next
    }
    while (match(line, /<!--/)) {
      pre = substr(line, 1, RSTART - 1)
      rest = substr(line, RSTART + 4)
      if (match(rest, /-->/)) {
        line = pre substr(rest, RSTART + 3)
      } else {
        line = pre
        c = 1
        break
      }
    }
    # Strip inline backtick code spans so legitimate code/HTML tags like `<button>` do not trigger
    gsub(/`[^`]*`/, "", line)
    if (line ~ /<[A-Z][A-Za-z0-9\/|_ -]*>/ || line ~ /<e\.g\.[^>]*>/ || line ~ /<measurable[^>]*>/) {
      printf "%d:%s\n", NR, $0
    }
  }
' "$file" | head -5)
[ -z "$ph" ] || missing="${missing}unfilled template placeholder(s):\n${ph}\n"

if [ -n "$missing" ]; then
  printf "FAIL (%s) %s:\n%b" "$mode" "$file" "$missing" >&2
  exit 1
fi

echo "PASS ($mode) $file"
exit 0
