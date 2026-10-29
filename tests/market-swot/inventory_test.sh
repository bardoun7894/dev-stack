#!/usr/bin/env bash
# Fixture test for skills/market-swot/scripts/inventory.sh
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
SCRIPT="$HERE/../../skills/market-swot/scripts/inventory.sh"
fail=0
command -v jq >/dev/null || { echo "FAIL jq not installed"; exit 1; }

# no arg -> exit 2
bash "$SCRIPT" >/dev/null 2>&1; rc=$?
[ "$rc" -eq 2 ] || { echo "FAIL no-arg exit want=2 got=$rc"; fail=1; }

T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
mkdir -p "$T/repo"; cd "$T/repo" || exit 1
git init -q; git config user.email t@e.com; git config user.name T
mkdir -p specs/001-a PRD app/dashboard app/pricing messages lib/screens
printf '# Acme Videos\n\nAI video maker for teams.\n' > README.md
echo '# prd' > PRD/prd.md
echo '# spec' > specs/001-a/spec.md
echo '{"dependencies":{"next":"14","react":"18"},"devDependencies":{"tailwindcss":"3"}}' > package.json
echo 'export default function P(){return null}' > app/dashboard/page.tsx
echo 'export default function P(){return "Pro $29/mo"}' > app/pricing/page.tsx
echo '{}' > messages/en.json; echo '{}' > messages/ar.json
echo '# design' > DESIGN.md
git add -A; git commit -q -m fx

out="$(bash "$SCRIPT" "$T/repo")"; rc=$?
[ "$rc" -eq 0 ] || { echo "FAIL exit=$rc"; fail=1; }
echo "$out" | jq . >/dev/null 2>&1 || { echo "FAIL not JSON"; echo "$out"; exit 1; }
for k in name specs stack routes i18n design_md; do
  echo "$out" | jq -e "has(\"$k\")" >/dev/null || { echo "FAIL key $k missing"; fail=1; }
done
[ "$(echo "$out" | jq -r .name)" = "Acme Videos" ] || { echo "FAIL name got=$(echo "$out" | jq -r .name)"; fail=1; }
[ "$(echo "$out" | jq -r '.specs[0]')" = "001-a" ] || { echo "FAIL specs"; fail=1; }
echo "$out" | jq -e '.stack | index("next")' >/dev/null || { echo "FAIL stack lacks next"; fail=1; }
echo "$out" | jq -e '.routes | map(select(test("dashboard"))) | length > 0' >/dev/null || { echo "FAIL routes lack dashboard"; fail=1; }
echo "$out" | jq -e '.i18n | (index("en") != null and index("ar") != null)' >/dev/null || { echo "FAIL i18n"; fail=1; }
[ "$(echo "$out" | jq -r .design_md)" = "DESIGN.md" ] || { echo "FAIL design_md"; fail=1; }
echo "$out" | jq -e '.pricing | length > 0' >/dev/null || { echo "FAIL pricing"; fail=1; }

[ "$fail" -eq 0 ] && echo "PASS all market-swot inventory_test.sh assertions"
exit $fail
