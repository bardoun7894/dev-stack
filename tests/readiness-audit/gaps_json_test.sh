#!/usr/bin/env bash
# Fixture test for skills/readiness-audit/scripts/gaps-json.sh
# Gap report (markdown) -> specs/_audit/<date>/gaps.json next to inventory.json.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
SK="$HERE/../../skills/readiness-audit/scripts"
fail=0
command -v jq >/dev/null || { echo "FAIL jq not installed"; exit 1; }

T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
A="$T/repo/specs/_audit/2026-01-02"; mkdir -p "$A"
cd "$T/repo" && git init -q && git config user.email t@e.com && git config user.name T
echo x > f && git add -A && git commit -q -m fixture
"$SK/inventory.sh" "$T/repo" > "$A/inventory.json"

cat > "$A/gap-report.md" <<'E'
# Gap Report — Fixture

## Findings

| Code | Source | Severity | Evidence | Verdict (after review) | Action |
|------|--------|----------|----------|------------------------|--------|
| G1   | PRD    | P1       | `backend/app/x.py:42` lacks `await` | confirmed | append tasks to spec 001 |
| G2   | checklist | P0    | `src/auth.ts` — no rate limit on login | confirmed | new spec |
| G3   | competitor | P2   | https://example.com/pricing — offers SSO | duplicate of 011 | drop |
| G4   | defect | P3     | stale `TODO` | confirmed | fix spec |
| G5   | spec   | p1     | spec 029 promises it | confirmed | report only |

### Severity

- **P0** — blocks production.
E

"$SK/gaps-json.sh" "$A/gap-report.md" "$A/gaps.json"; rc=$?
[ "$rc" -eq 0 ] || { echo "FAIL exit=$rc"; fail=1; }
[ -f "$A/inventory.json" ] && [ -f "$A/gaps.json" ] || { echo "FAIL gaps.json not next to inventory.json"; fail=1; }
jq -e 'length==5 and all(.[]; (.code|test("^G[0-9]+$")) and (.text|length>0) and (.severity|test("^P[0-3]$")))' "$A/gaps.json" >/dev/null \
  || { echo "FAIL shape"; cat "$A/gaps.json"; fail=1; }
[ "$(jq -r '[.[].code]|join(",")' "$A/gaps.json")" = "G1,G2,G3,G4,G5" ] || { echo "FAIL codes"; fail=1; }
[ "$(jq -r '[.[].severity]|join(",")' "$A/gaps.json")" = "P1,P0,P2,P3,P1" ] || { echo "FAIL severities"; fail=1; }
[ "$(jq -r '.[1].source' "$A/gaps.json")" = checklist ] || { echo "FAIL source"; fail=1; }
jq -e '.[0].text|contains("lacks")' "$A/gaps.json" >/dev/null || { echo "FAIL text from evidence"; fail=1; }
cmp -s "$A/gap-report.md" <(cat "$A/gap-report.md") && grep -q '^| G1' "$A/gap-report.md" || { echo "FAIL markdown report must stay"; fail=1; }

# no gaps -> []
printf '# Gap Report\n\n## Findings\n\n| Code | Source | Severity | Evidence | Verdict (after review) | Action |\n|------|--------|----------|----------|------|------|\n' > "$T/none.md"
"$SK/gaps-json.sh" "$T/none.md" "$T/none.json"
[ "$(jq -c . "$T/none.json")" = "[]" ] || { echo "FAIL empty want []"; fail=1; }

# missing severity word is rejected, not guessed
printf '| G1 | PRD | | e | confirmed | x |\n' > "$T/bad.md"
"$SK/gaps-json.sh" "$T/bad.md" "$T/bad.json" 2>/dev/null && { echo "FAIL missing severity should fail"; fail=1; }

[ "$fail" -eq 0 ] && echo "PASS gaps_json_test"
exit "$fail"
