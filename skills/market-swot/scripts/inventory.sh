#!/usr/bin/env bash
# skills/market-swot/scripts/inventory.sh <repo>
# Zero-AI inventory of a project for SWOT/competitor research. JSON to stdout.
set -u
REPO="${1:-}"
if [ -z "$REPO" ] || [ ! -d "$REPO" ]; then
  echo "usage: $0 <repo-path>" >&2
  exit 2
fi
REPO="$(cd "$REPO" && pwd)"
command -v jq >/dev/null || { echo "jq required" >&2; exit 1; }

if [ -d "$REPO/.git" ]; then
  FILES="$(git -C "$REPO" ls-files 2>/dev/null)"
else
  FILES="$(cd "$REPO" && find . -maxdepth 5 \( -name node_modules -o -name vendor -o -name .git -o -name build -o -name dist -o -name .next \) -prune -o -type f -print 2>/dev/null | sed 's|^\./||')"
fi
lines() { awk 'NF' | jq -R . | jq -s .; }

# name + readme
readme=""
for f in README.md readme.md Readme.md; do [ -f "$REPO/$f" ] && readme="$REPO/$f" && break; done
name="$(basename "$REPO")"; para=""
if [ -n "$readme" ]; then
  h="$(grep -m1 -E '^#[[:space:]]+' "$readme" | sed -E 's/^#+[[:space:]]+//')"
  [ -n "$h" ] && name="$h"
  para="$(awk '/^#/{next} NF{print; found=1; next} found{exit}' "$readme" | head -3 | tr '\n' ' ')"
fi

prd="$(echo "$FILES" | grep -E '(^|/)(PRD/|PRD\.md$|prd\.md$|docs/prd|docs/PRD)|requirements.*\.md$' | lines)"
specs="[]"
if [ -d "$REPO/specs" ]; then
  specs="$(ls -1 "$REPO/specs" 2>/dev/null | grep -E '^[0-9]{3}-' | lines)"
fi

# stack: dependency keys
stack_raw=""
while IFS= read -r m; do
  [ -f "$REPO/$m" ] || continue
  case "$m" in
    *package.json) stack_raw="$stack_raw
$(jq -r '(.dependencies // {}) + (.devDependencies // {}) | keys[]' "$REPO/$m" 2>/dev/null)" ;;
    *composer.json) stack_raw="$stack_raw
$(jq -r '(.require // {}) + (.["require-dev"] // {}) | keys[]' "$REPO/$m" 2>/dev/null)" ;;
    *pubspec.yaml) stack_raw="$stack_raw
$(awk '/^(dependencies|dev_dependencies):/{d=1;next} /^[^ ]/{d=0} d && /^  [a-zA-Z_]+:/{sub(/:.*/,"");gsub(/ /,"");print}' "$REPO/$m")" ;;
  esac
done <<< "$(echo "$FILES" | grep -E '(^|/)(package\.json|composer\.json|pubspec\.yaml)$' | grep -v node_modules | head -10)"
stack="$(echo "$stack_raw" | lines | jq 'unique')"

# routes / screens
routes="$( {
  echo "$FILES" | grep -E '(^|/)(app|pages)/.*(page|index)\.(tsx|jsx|ts|js|vue)$|(^|/)pages/[^/]+\.(tsx|jsx|vue)$' | grep -v node_modules
  echo "$FILES" | grep -E '(^|/)lib/screens/.*\.dart$'
  echo "$FILES" | grep -E '(^|/)routes/web\.php$' | while read -r r; do
    n=$(grep -cE 'Route::(get|post|put|patch|delete|resource|view)' "$REPO/$r" 2>/dev/null || echo 0)
    echo "$r (laravel routes: $n)"
  done
} | lines)"

# pricing strings
pricing="$( cd "$REPO" && echo "$FILES" | grep -E '\.(tsx|jsx|ts|js|vue|php|blade\.php|md|json|dart)$' | grep -v node_modules | head -400 \
  | xargs grep -HoiE '(\$|€|USD |EUR )[0-9]+([.,][0-9]+)?[ ]?(/|per )?(mo|month|yr|year)?|(price|pricing|plan)s?[:"= ]+[A-Za-z ]{0,20}[0-9]+' 2>/dev/null | head -20 | lines)"

# i18n locales
i18n="$( echo "$FILES" | grep -E '(^|/)(locales|l10n|lang|messages|i18n|translations)/[^/]+\.(json|php|arb|ya?ml)$|\.arb$' \
  | sed -E 's|.*/||; s|^app_||; s|\.[a-z]+$||' | sort -u | lines)"

design="$(echo "$FILES" | grep -E '(^|/)DESIGN\.md$' | head -1)"

jq -n --arg repo "$REPO" --arg name "$name" --arg readme_para "$para" \
  --argjson prd "$prd" --argjson specs "$specs" --argjson stack "$stack" \
  --argjson routes "$routes" --argjson pricing "$pricing" --argjson i18n "$i18n" \
  --arg design "$design" \
  '{repo:$repo,name:$name,readme_para:$readme_para,prd:$prd,specs:$specs,stack:$stack,routes:$routes,pricing:$pricing,i18n:$i18n,design_md:(if $design=="" then null else $design end)}'
