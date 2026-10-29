#!/bin/bash
# bash tests/test_verify_env_guard.sh — scripts/gate/verify-env-guard.sh (G18): verifier refuses prod DB/env
S="$(cd "$(dirname "$0")/.." && pwd)/scripts/gate/verify-env-guard.sh"
T=$(mktemp -d); fails=0

check() { # name expected_rc repo_dir [expected_substr]
  local out rc
  out=$(env -i PATH="$PATH" HOME="$HOME" "$S" "$3" 2>&1); rc=$?
  if [ "$rc" = "$2" ] && { [ -z "${4:-}" ] || printf '%s' "$out" | grep -qi "$4"; }; then
    echo "ok   $1"
  else
    echo "FAIL $1 (rc=$rc, want $2, match '${4:-}') out=$out"
    fails=1
  fi
}

# 1. Clean local env
mkdir -p "$T/clean"
printf 'APP_ENV=local\nNODE_ENV=development\nDATABASE_URL=postgres://postgres:postgres@127.0.0.1:5432/app_test\nDB_HOST=127.0.0.1\nDB_DATABASE=app_test\n' > "$T/clean/.env"
check clean-local 0 "$T/clean"

# 2. APP_ENV=production in .env
mkdir -p "$T/app-prod"
printf 'APP_ENV=production\nDATABASE_URL=postgres://127.0.0.1:5432/test\n' > "$T/app-prod/.env"
check app-env-prod 1 "$T/app-prod" "APP_ENV"

# 3. NODE_ENV=production in .env.local
mkdir -p "$T/node-prod"
printf 'NODE_ENV="production"\n' > "$T/node-prod/.env.local"
check node-env-prod 1 "$T/node-prod" "NODE_ENV"

# 4. Supabase pooler host in DATABASE_URL
mkdir -p "$T/supabase"
printf 'DATABASE_URL=postgresql://postgres.ref:pass@aws-0-eu-central-1.pooler.supabase.com:6543/postgres\n' > "$T/supabase/.env"
check supabase-pooler 1 "$T/supabase" "DATABASE_URL"

# 5. RDS host in DB_HOST (.env.testing)
mkdir -p "$T/rds"
printf 'DB_HOST=mydb.c9akciq32.us-east-1.rds.amazonaws.com\n' > "$T/rds/.env.testing"
check rds-host 1 "$T/rds" "DB_HOST"

# 6. 'prod' or 'production' word in DB_DATABASE or DB_HOST
mkdir -p "$T/prod-word"
printf 'DB_DATABASE=mediatgb_prod\n' > "$T/prod-word/.env"
check db-name-prod 1 "$T/prod-word" "DB_DATABASE"

mkdir -p "$T/production-word"
printf 'DATABASE_URL=postgres://user:pass@db-production.internal:5432/app\n' > "$T/production-word/.env"
check url-production-host 1 "$T/production-word" "DATABASE_URL"

# 7. Substring 'product' or 'reproduce' must NOT false-positive
mkdir -p "$T/product-safe"
printf 'DB_DATABASE=products_catalog_dev\nDB_HOST=reproduce-issue.local\n# DATABASE_URL=postgres://prod.rds.amazonaws.com/prod\n' > "$T/product-safe/.env"
check product-substring-safe 0 "$T/product-safe"

# 8. Current environment variable refused even if .env is clean
out=$(env -i PATH="$PATH" HOME="$HOME" DATABASE_URL="postgres://u:p@db.xyz.supabase.co:5432/postgres" "$S" "$T/clean" 2>&1); rc=$?
[ "$rc" = 1 ] && printf '%s' "$out" | grep -qi "DATABASE_URL" && echo "ok   env-var-prod" || { echo "FAIL env-var-prod (rc=$rc, out=$out)"; fails=1; }

# 9. VERIFY_PROD_OK=1 bypasses with stderr warning
out=$(env -i PATH="$PATH" HOME="$HOME" VERIFY_PROD_OK=1 "$S" "$T/supabase" 2>&1 >/dev/null); rc=$?
[ "$rc" = 0 ] && printf '%s' "$out" | grep -qi "VERIFY_PROD_OK" && echo "ok   bypass-warn" || { echo "FAIL bypass-warn (rc=$rc, out=$out)"; fails=1; }

rm -rf "$T"; exit $fails
