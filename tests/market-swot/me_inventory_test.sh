#!/usr/bin/env bash
# Fixture test for skills/market-swot/scripts/me-inventory.sh
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
SCRIPT="$HERE/../../skills/market-swot/scripts/me-inventory.sh"
fail=0
command -v jq >/dev/null || { echo "FAIL jq not installed"; exit 1; }
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
mkdir -p "$T/portfolio/content" "$T/projects/alpha" "$T/projects/beta" "$T/bin"
echo '# about' > "$T/portfolio/content/about.md"
cat > "$T/mem.md" <<'E'
# Memory Index

- [Alpha thing](alpha.md) — hook one
- [Beta thing](beta.md) — hook two
E
cat > "$T/bin/gh" <<'E'
#!/usr/bin/env bash
echo '[{"name":"repo1","description":"d","stargazerCount":3,"updatedAt":"2026-01-01T00:00:00Z"}]'
E
chmod +x "$T/bin/gh"
export PORTFOLIO_DIR="$T/portfolio" PROJECTS_DIR="$T/projects" MEMORY_INDEX="$T/mem.md"

out="$(PATH="$T/bin:$PATH" bash "$SCRIPT")"; rc=$?
[ "$rc" -eq 0 ] || { echo "FAIL exit=$rc"; fail=1; }
echo "$out" | jq . >/dev/null 2>&1 || { echo "FAIL not JSON"; echo "$out"; exit 1; }
for k in portfolio github projects memory; do
  echo "$out" | jq -e "has(\"$k\")" >/dev/null || { echo "FAIL key $k missing"; fail=1; }
done
[ "$(echo "$out" | jq -r .github.gh_available)" = "true" ] || { echo "FAIL gh_available want=true"; fail=1; }
[ "$(echo "$out" | jq -r '.github.repos[0].name')" = "repo1" ] || { echo "FAIL github repos"; fail=1; }
echo "$out" | jq -e '.portfolio.content_files | map(select(test("about.md"))) | length == 1' >/dev/null || { echo "FAIL portfolio files"; fail=1; }
[ "$(echo "$out" | jq -r '.projects | length')" = "2" ] || { echo "FAIL projects count"; fail=1; }
[ "$(echo "$out" | jq -r .memory.count)" = "2" ] || { echo "FAIL memory count got=$(echo "$out" | jq -r .memory.count)"; fail=1; }

# failing gh
cat > "$T/bin/gh" <<'E'
#!/usr/bin/env bash
exit 1
E
out2="$(PATH="$T/bin:$PATH" bash "$SCRIPT")"
[ "$(echo "$out2" | jq -r .github.gh_available)" = "false" ] || { echo "FAIL gh_available want=false on gh failure"; fail=1; }

[ "$fail" -eq 0 ] && echo "PASS all market-swot me_inventory_test.sh assertions"
exit $fail
