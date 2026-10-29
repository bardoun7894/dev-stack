#!/bin/bash
# verify-env-guard.sh <repo> (G18)
# Reads <repo>/.env, .env.local, .env.testing plus current env for DATABASE_URL, DB_HOST, DB_DATABASE, APP_ENV, NODE_ENV.
# Exits 1 with a one-line reason if APP_ENV/NODE_ENV=production or a DB host/URL/name matches prod-db-patterns.txt.
# VERIFY_PROD_OK=1 bypasses with a stderr warning.
set -u
[ $# -ge 1 ] || { echo "usage: verify-env-guard.sh <repo>" >&2; exit 2; }
repo="$1"
[ -d "$repo" ] || { echo "verify-env-guard: no such directory: $repo" >&2; exit 2; }

if [ "${VERIFY_PROD_OK:-}" = "1" ]; then
  echo "WARN verify-env-guard: VERIFY_PROD_OK=1 set, bypassing prod DB guard for $repo" >&2
  exit 0
fi

DIR="$(cd "$(dirname "$0")" && pwd)"
PAT_FILE="${VERIFY_PROD_PATTERNS:-$DIR/prod-db-patterns.txt}"
[ -f "$PAT_FILE" ] || { echo "verify-env-guard: missing pattern file: $PAT_FILE" >&2; exit 2; }

check_kv() { # source key val
  local src="$1" k="$2" v="$3" pat regex
  [ -n "$v" ] || return 0
  case "$k" in
    APP_ENV|NODE_ENV)
      if printf '%s' "$v" | grep -qiE '^production$'; then
        echo "REFUSED verify-env-guard: $src sets $k=$v (production environment)" >&2
        exit 1
      fi
      ;;
    DATABASE_URL|DB_HOST|DB_DATABASE)
      while IFS= read -r pat || [ -n "$pat" ]; do
        pat=$(printf '%s' "$pat" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
        case "$pat" in
          ""|\#*) continue ;;
        esac
        # Convert leading '*.' glob shorthand to a portable ERE host prefix
        regex=$(printf '%s' "$pat" | sed 's/^\*\./[^[:space:]@:\/]*\\./')
        if printf '%s' "$v" | grep -qiE "$regex"; then
          echo "REFUSED verify-env-guard: $src $k matches prod pattern '$pat'" >&2
          exit 1
        fi
      done < "$PAT_FILE"
      ;;
  esac
}

# 1. Check current environment variables
for k in APP_ENV NODE_ENV DATABASE_URL DB_HOST DB_DATABASE; do
  eval "val=\${$k:-}"
  [ -n "$val" ] && check_kv "env" "$k" "$val"
done

# 2. Check <repo>/.env, .env.local, .env.testing
for f in .env .env.local .env.testing; do
  fp="$repo/$f"
  [ -f "$fp" ] || continue
  while IFS= read -r line || [ -n "$line" ]; do
    line=$(printf '%s' "$line" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
    case "$line" in
      ""|\#*) continue ;;
    esac
    line=${line#export }
    case "$line" in
      *=*)
        k=$(printf '%s' "${line%%=*}" | tr -d '[:space:]')
        v="${line#*=}"
        # Strip inline unquoted comment or surrounding quotes
        case "$v" in
          \"*\") v="${v#\"}"; v="${v%\"}" ;;
          \'*\') v="${v#\'}"; v="${v%\'}" ;;
          *) v=$(printf '%s' "$v" | sed 's/[[:space:]]*#.*$//') ;;
        esac
        case "$k" in
          APP_ENV|NODE_ENV|DATABASE_URL|DB_HOST|DB_DATABASE)
            check_kv "$f" "$k" "$v"
            ;;
        esac
        ;;
    esac
  done < "$fp"
done

exit 0
