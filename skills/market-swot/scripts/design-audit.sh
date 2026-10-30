#!/usr/bin/env bash
# skills/market-swot/scripts/design-audit.sh <repo> [url]
# Zero-AI evidence for the design audit mode. JSON to stdout. Offline-safe.
set -u
REPO="${1:-}"; URL="${2:-}"
if [ -z "$REPO" ] || [ ! -d "$REPO" ]; then echo "usage: $0 <repo> [url]" >&2; exit 2; fi
REPO="$(cd "$REPO" && pwd)"
command -v jq >/dev/null || { echo "jq required" >&2; exit 1; }
if [ -d "$REPO/.git" ]; then FILES="$(git -C "$REPO" ls-files 2>/dev/null)"
else FILES="$(cd "$REPO" && find . -maxdepth 6 \( -name node_modules -o -name vendor -o -name .git -o -name .next -o -name dist -o -name build \) -prune -o -type f -print | sed 's|^\./||')"; fi

# --- deps vs latest (package.json) ---
WATCH='^(tailwindcss|framer-motion|motion|gsap|shadcn|shadcn-ui|next|react|lottie-react|lottie-web|@lottiefiles/.*|@rive-app/.*|rive-react|@radix-ui/.*)$'
deps='[]'
while IFS= read -r pj; do
  [ -f "$REPO/$pj" ] || continue
  while IFS=$'\t' read -r pkg cur; do
    [ -n "$pkg" ] || continue
    latest="$(timeout 15 npm view "$pkg" version 2>/dev/null | head -1)"
    deps="$(echo "$deps" | jq --arg p "$pkg" --arg c "$cur" --arg l "$latest" --arg f "$pj" \
      '. + [{pkg:$p,current:$c,latest:(if $l=="" then null else $l end),file:$f,
             outdated:(if $l=="" then null else (($c|gsub("^[^0-9]*";"")|split(".")[0]) != ($l|split(".")[0])) end)}]')"
  done < <(jq -r '(.dependencies // {}) + (.devDependencies // {}) | to_entries[] | select(.key|test("'"$WATCH"'")) | "\(.key)\t\(.value)"' "$REPO/$pj" 2>/dev/null)
done <<< "$(echo "$FILES" | grep -E '(^|/)package\.json$' | grep -v node_modules | head -5)"
composer='null'
if [ -f "$REPO/composer.lock" ] && command -v composer >/dev/null 2>&1; then
  composer="$( (cd "$REPO" && timeout 60 composer outdated --direct --format=json 2>/dev/null) | jq -c '.installed // null' 2>/dev/null || echo null)"
  [ -n "$composer" ] || composer='null'
fi

# --- lighthouse / axe ---
lighthouse='null'; axe='null'
if [ -n "$URL" ] && command -v npx >/dev/null 2>&1; then
  lh="$(timeout 180 npx --no-install lighthouse "$URL" --output=json --quiet --chrome-flags=--headless 2>/dev/null)"
  [ -n "$lh" ] && lighthouse="$(echo "$lh" | jq -c '{performance:(.categories.performance.score),accessibility:(.categories.accessibility.score),best_practices:(.categories["best-practices"].score),seo:(.categories.seo.score)}' 2>/dev/null || echo null)"
  ax="$(timeout 120 npx --no-install @axe-core/cli "$URL" --stdout 2>/dev/null)"
  [ -n "$ax" ] && axe="$(echo "$ax" | jq -c '.[0].violations | length' 2>/dev/null || echo null)"
  [ -n "$lighthouse" ] || lighthouse='null'; [ -n "$axe" ] || axe='null'
fi

# --- design files ---
design="$(echo "$FILES" | grep -E '(^|/)DESIGN\.md$' | head -1)"
tokens="$(echo "$FILES" | grep -E '(^|/)(tokens\.json|design-tokens\.json|tailwind\.config\.[a-z]+|theme\.(ts|js|css))$' | head -1)"

# --- old-pattern signals ---
code="$(echo "$FILES" | grep -E '\.(css|scss|sass|less|html|htm|tsx|jsx|vue|php|js|ts|svelte|dart)$' | grep -vE '\.min\.|node_modules|vendor/')"
cnt() { [ -n "$code" ] && (cd "$REPO" && echo "$code" | xargs grep -hoE "$1" 2>/dev/null | wc -l | tr -d ' ') || echo 0; }
has() { [ "$(cnt "$1")" -gt 0 ] && echo true || echo false; }
pj_all="$(cd "$REPO" && echo "$FILES" | grep -E '(^|/)package\.json$' | grep -v node_modules | xargs cat 2>/dev/null)"
jq_sig=$(echo "$pj_all" | grep -qE '"jquery"' && echo true || has 'jquery[.-][0-9a-z.]*js|\$\(document\)\.ready')
bs_sig=$(echo "$pj_all" | grep -qE '"bootstrap": *"[^"]*[34]\.' && echo true || has 'bootstrap[/@-][34]\.')
important="$(cnt '!important')"
inline="$(cnt 'style="[^"]*"')"
rm_present="$(cnt 'prefers-reduced-motion')"
[ "$rm_present" -gt 0 ] && rm_missing=false || rm_missing=true
old_fonts="$(cnt 'font-family:[^;]*(Arial|Helvetica|Times New Roman|Verdana|Tahoma)[^;]*;')"
px_n="$(cnt '(margin|padding|gap)[a-z-]*:[^;]*[0-9]+px')"
rem_n="$(cnt '(margin|padding|gap)[a-z-]*:[^;]*[0-9.]+(rem|em)')"
[ "$px_n" -gt 0 ] && [ "$rem_n" -eq 0 ] && px_only=true || px_only=false

jq -n --arg repo "$REPO" --arg url "$URL" --argjson deps "$deps" --argjson composer "$composer" \
  --argjson lighthouse "$lighthouse" --argjson axe "$axe" --arg design "$design" --arg tokens "$tokens" \
  --argjson jq "$jq_sig" --argjson bs "$bs_sig" --argjson imp "$important" --argjson inl "$inline" \
  --argjson rm "$rm_missing" --argjson fonts "$old_fonts" --argjson px "$px_only" \
  '{repo:$repo,url:(if $url=="" then null else $url end),deps:$deps,composer_outdated:$composer,lighthouse:$lighthouse,axe:$axe,
    design_md:(if $design=="" then null else $design end),tokens_file:(if $tokens=="" then null else $tokens end),
    signals:{jquery:$jq,bootstrap:$bs,important_count:$imp,inline_style_count:$inl,reduced_motion_missing:$rm,old_font_stack_count:$fonts,px_only_spacing:$px}}'
