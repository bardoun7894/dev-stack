#!/usr/bin/env bash
# Fixture test for skills/readiness-audit/scripts/inventory.sh
# Builds a synthetic git repo in a temp dir, runs inventory.sh, asserts JSON.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
SCRIPT="$HERE/../../skills/readiness-audit/scripts/inventory.sh"
fail=0

# Pre-flight: jq required
command -v jq >/dev/null || { echo "FAIL jq not installed"; exit 1; }

T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
mkdir -p "$T/repo"
cd "$T/repo" || exit 1
git init -q
git config user.email test@example.com
git config user.name "Test"
mkdir -p specs/001-a specs/002-b PRD src
cat > specs/001-a/spec.md   <<'E'
# spec
E
cat > specs/001-a/plan.md   <<'E'
# plan
E
cat > specs/001-a/tasks.md  <<'E'
# tasks
- [ ] open one
- [ ] open two
- [x] done one
E
cat > specs/002-b/spec.md   <<'E'
# spec b
E
cat > PRD/prd.md            <<'E'
# PRD
E
cat > src/x.js              <<'E'
// TODO: implement feature
function noop() { return null; }
E
cat > .env.example          <<'E'
KEY=val
E
git add -A
git commit -q -m "fixture"

# 1. inventory.sh must succeed and emit valid JSON
out="$("$SCRIPT" "$T/repo")"; rc=$?
if [ "$rc" -ne 0 ]; then echo "FAIL inventory.sh exit=$rc"; fail=1; fi
echo "$out" | jq . >/dev/null 2>&1 || { echo "FAIL output not valid JSON"; fail=1; }
if [ "$fail" -ne 0 ]; then echo "---raw---"; echo "$out"; exit 1; fi

# 2. repo path is recorded
got_repo=$(echo "$out" | jq -r .repo)
[ "$got_repo" = "$T/repo" ] || { echo "FAIL repo want=$T/repo got=$got_repo"; fail=1; }

# 3. git branch/head/dirty present
echo "$out" | jq -e '.git.branch' >/dev/null 2>&1 || { echo "FAIL git.branch missing"; fail=1; }
echo "$out" | jq -e '.git.head'   >/dev/null 2>&1 || { echo "FAIL git.head missing"; fail=1; }
[ "$(echo "$out" | jq -r .git.dirty)" = "false" ] || { echo "FAIL git.dirty want=false"; fail=1; }

# 4. prd list contains PRD/prd.md
prd_paths=$(echo "$out" | jq -r '.prd[]')
echo "$prd_paths" | grep -q 'PRD/prd.md' || { echo "FAIL prd missing PRD/prd.md"; fail=1; }

# 5. specs array — 001-a has open=2 done=1, 002-b has spec only
n_specs=$(echo "$out" | jq '.specs | length')
[ "$n_specs" = "2" ] || { echo "FAIL specs.length want=2 got=$n_specs"; fail=1; }

a_open=$(echo "$out" | jq '.specs[] | select(.id=="001-a") | .open')
a_done=$(echo "$out" | jq '.specs[] | select(.id=="001-a") | .done')
a_has_plan=$(echo "$out" | jq '.specs[] | select(.id=="001-a") | .has_plan')
[ "$a_open" = "2" ]  || { echo "FAIL 001-a open want=2 got=$a_open"; fail=1; }
[ "$a_done" = "1" ]  || { echo "FAIL 001-a done want=1 got=$a_done"; fail=1; }
[ "$a_has_plan" = "true" ] || { echo "FAIL 001-a has_plan want=true got=$a_has_plan"; fail=1; }

b_has_spec=$(echo "$out"  | jq '.specs[] | select(.id=="002-b") | .has_spec')
b_has_plan=$(echo "$out"  | jq '.specs[] | select(.id=="002-b") | .has_plan')
[ "$b_has_spec" = "true" ]  || { echo "FAIL 002-b has_spec want=true got=$b_has_spec"; fail=1; }
[ "$b_has_plan" = "false" ] || { echo "FAIL 002-b has_plan want=false got=$b_has_plan"; fail=1; }

# 6. signals — tests/ci false (none here), env_example true, dockerfile false,
#    health_route false, migrations false, i18n false, error_tracking false,
#    legal_pages false, backups false
[ "$(echo "$out" | jq -r .signals.env_example)" = "true" ]  || { echo "FAIL env_example want=true"; fail=1; }
[ "$(echo "$out" | jq -r .signals.dockerfile)" = "false" ] || { echo "FAIL dockerfile want=false"; fail=1; }
[ "$(echo "$out" | jq -r .signals.health_route)" = "false" ]|| { echo "FAIL health_route want=false"; fail=1; }

# 7. stubs count >= 1 (TODO in src/x.js)
stubs=$(echo "$out" | jq -r .signals.stubs)
if [ "$stubs" -lt 1 ] 2>/dev/null; then echo "FAIL stubs want>=1 got=$stubs"; fail=1; fi

# 8. generated_at present and ISO 8601-shaped
ts=$(echo "$out" | jq -r .generated_at)
echo "$ts" | grep -qE '^[0-9]{4}-[0-9]{2}-[0-9]{2}T' || { echo "FAIL generated_at shape: $ts"; fail=1; }

# 9. Monorepo fixture — signals must be detected in nested paths
M="$(mktemp -d)"; trap 'rm -rf "$T" "$M"' EXIT
mkdir -p "$M/repo"
cd "$M/repo" || exit 1
git init -q
git config user.email test@example.com
git config user.name "Test"
# monorepo tree: backend (Laravel-ish) + frontend (Next-ish) + infra
mkdir -p backend/tests/Feature backend/database/migrations \
         frontend/tests frontend/messages frontend/src/app/privacy infra
cat > backend/tests/FooTest.php <<'E'
<?php class FooTest {}
E
cat > backend/database/migrations/2024_01_01_create_x.php <<'E'
<?php // migration
E
cat > frontend/.env.example <<'E'
KEY=val
E
cat > frontend/messages/en.json <<'E'
{ "greeting": "hi" }
E
cat > frontend/src/app/privacy/page.tsx <<'E'
export default function Page() { return null; }
E
cat > infra/docker-compose.yml <<'E'
services: {}
E
git add -A
git commit -q -m "monorepo fixture"
out_m="$("$SCRIPT" "$M/repo")"; rc=$?
if [ "$rc" -ne 0 ]; then echo "FAIL monorepo inventory exit=$rc"; fail=1; fi
echo "$out_m" | jq . >/dev/null 2>&1 || { echo "FAIL monorepo output not JSON"; fail=1; }
[ "$(echo "$out_m" | jq -r .signals.tests)"        = "true" ] || { echo "FAIL monorepo .signals.tests want=true got=$(echo "$out_m" | jq -r .signals.tests)"; fail=1; }
[ "$(echo "$out_m" | jq -r .signals.migrations)"   = "true" ] || { echo "FAIL monorepo .signals.migrations want=true got=$(echo "$out_m" | jq -r .signals.migrations)"; fail=1; }
[ "$(echo "$out_m" | jq -r .signals.env_example)"  = "true" ] || { echo "FAIL monorepo .signals.env_example want=true"; fail=1; }
[ "$(echo "$out_m" | jq -r .signals.i18n)"         = "true" ] || { echo "FAIL monorepo .signals.i18n want=true"; fail=1; }
[ "$(echo "$out_m" | jq -r .signals.legal_pages)"  = "true" ] || { echo "FAIL monorepo .signals.legal_pages want=true"; fail=1; }
[ "$(echo "$out_m" | jq -r .signals.dockerfile)"   = "true" ] || { echo "FAIL monorepo .signals.dockerfile want=true"; fail=1; }
# stubs is a top-level number
stubs_top=$(echo "$out_m" | jq -r .stubs)
echo "$stubs_top" | grep -qE '^[0-9]+$' || { echo "FAIL monorepo .stubs not a number: $stubs_top"; fail=1; }

if [ "$fail" -eq 0 ]; then echo "PASS all inventory_test.sh assertions"; fi
exit $fail