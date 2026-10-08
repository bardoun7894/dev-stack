#!/usr/bin/env bash
# skills/readiness-audit/scripts/inventory.sh <repo>
# Deterministic inventory of a project repo. Prints JSON to stdout. No AI.
#
# Performance: uses `git ls-files` / `git grep` when inside a git repo, so a
# large repo runs in well under 30s. Outside git it falls back to `find` with
# bounded depth.
set -u

REPO="${1:-}"
if [ -z "$REPO" ] || [ ! -d "$REPO" ]; then
  echo "usage: $0 <repo-path>" >&2
  exit 2
fi
REPO="$(cd "$REPO" && pwd)"

now() { date -u +"%Y-%m-%dT%H:%M:%SZ"; }
GENERATED_AT="$(now)"

# --- helpers ---------------------------------------------------------------
# Run a command inside REPO; capture stdout. Trim trailing whitespace.
run_in() { ( cd "$REPO" && "$@" ); }

# git ls-files prints paths relative to repo root. Empty string if not a repo
# or repo has no tracked files.
git_ls_files() {
  if [ -d "$REPO/.git" ]; then
    git -C "$REPO" ls-files 2>/dev/null || true
  fi
}

# git_grep <pattern> [extra-git-grep-args...] — uses git grep when available
# for speed; falls back to grep -rI on a bounded file list otherwise.
git_grep() {
  local pat="$1"; shift
  if [ -d "$REPO/.git" ]; then
    git -C "$REPO" grep -Il --color=never -E "$pat" "$@" 2>/dev/null || true
  else
    # bounded fallback: top 3 levels, exclude vendor/build
    grep -rIl --include='*' \
      --exclude-dir=node_modules --exclude-dir=vendor --exclude-dir=.git \
      --exclude-dir=build --exclude-dir=dist --exclude-dir=.next \
      --exclude-dir=.cache --exclude-dir=__pycache__ \
      -E "$pat" "$REPO" 2>/dev/null | head -2000 || true
  fi
}

# --- git info --------------------------------------------------------------
git_branch=""; git_head=""; git_dirty="false"
if [ -d "$REPO/.git" ]; then
  git_branch="$(git -C "$REPO" rev-parse --abbrev-ref HEAD 2>/dev/null || echo '')"
  git_head="$(git -C "$REPO" rev-parse --short HEAD 2>/dev/null || echo '')"
  # dirty if any tracked file differs from index, or untracked changes in src/specs
  if ! git -C "$REPO" diff --quiet --ignore-submodules 2>/dev/null \
     || [ -n "$(git -C "$REPO" ls-files --others --exclude-standard 2>/dev/null | head -1)" ]; then
    git_dirty="true"
  fi
fi

# --- PRD paths -------------------------------------------------------------
# Paths matching PRD/*, docs/prd*, *requirements*.md at depth<=3, repo-relative.
prd_json="[]"
prd_files="$(run_in bash -c '
  for f in $(git ls-files 2>/dev/null) $(find . -maxdepth 3 -type f \
    -not -path "./.git/*" -not -path "./node_modules/*" -not -path "./vendor/*" 2>/dev/null); do
    case "$f" in
      ./.) continue ;;
      ./.git/*|./*/.git/*) continue ;;
    esac
    rel="${f#./}"
    case "$rel" in
      PRD/*|PRD.md|prd.md|docs/prd*|docs/PRD*|*requirements*.md|*Requirements*.md)
        echo "$rel" ;;
    esac
  done
' | sort -u)"
# dedupe and emit as JSON array
prd_json="$(printf '%s\n' "$prd_files" | awk 'NF' | jq -R 'select(length>0) ' | jq -s 'unique')"

# --- specs -----------------------------------------------------------------
# For each specs/NNN-*/ directory, capture id, has_spec, has_plan, has_tasks,
# open count, done count from tasks.md.
specs_json="[]"
specs_dir="$REPO/specs"
if [ -d "$specs_dir" ]; then
  for d in "$specs_dir"/*; do
    [ -d "$d" ] || continue
    base="$(basename "$d")"
    case "$base" in
      [0-9][0-9][0-9]-*) : ;;      # matches NNN-*
      *) continue ;;
    esac
    id="$base"
    has_spec="false"; has_plan="false"; has_tasks="false"
    [ -f "$d/spec.md"  ] && has_spec="true"
    [ -f "$d/plan.md"  ] && has_plan="true"
    [ -f "$d/tasks.md" ] && has_tasks="true"
    open=0; done=0
    if [ -f "$d/tasks.md" ]; then
      open=$(grep -cE '^[[:space:]]*-[[:space:]]\[[[:space:]\]' "$d/tasks.md" 2>/dev/null || true)
      done=$(grep -cE '^[[:space:]]*-[[:space:]]\[[xX]\]' "$d/tasks.md" 2>/dev/null || true)
      open="${open:-0}"; done="${done:-0}"
    fi
    item="$(jq -n \
      --arg id "$id" \
      --argjson has_spec "$has_spec" \
      --argjson has_plan "$has_plan" \
      --argjson has_tasks "$has_tasks" \
      --argjson open "$open" \
      --argjson done "$done" \
      '{id:$id, has_spec:$has_spec, has_plan:$has_plan, has_tasks:$has_tasks, open:$open, done:$done}')"
    specs_json="$(echo "$specs_json" | jq --argjson item "$item" '. + [$item]')"
  done
fi

# --- signals ---------------------------------------------------------------
# tests:        any test dir / test config file
# ci:           .github/workflows/*.yml or .gitlab-ci.yml or .circleci/config.yml
# env_example:  .env.example or env.example
# dockerfile:    Dockerfile or docker-compose*.yml
# health_route: any tracked file matching /health (excluded dirs)
# migrations:   migrations/ db/migrations/ alembic/ prisma/ schema.sql
# i18n:         locales/ l10n/ lang/ messages/ *.arb
# error_tracking: sentry|bugsnag|rollbar mentioned in package manifests / requirements
# legal_pages:  privacy|terms files / routes
# backups:      backup in scripts/ ops/ infra/ dirs
# stubs:        count of TODO|FIXME|NotImplemented in source files (excluded dirs)
#
# Each signal is computed via git grep when possible, else a bounded find+grep.
lsf="$(git_ls_files)"

has_path() { # has_path <needle>
  local needle="$1"
  echo "$lsf" | grep -qx "$needle" 2>/dev/null && return 0
  echo "$lsf" | grep -qE "(^|/)$needle\$" 2>/dev/null && return 0
  return 1
}

bool_signal() { # bool_signal <name> -> "true"|"false"
  case "$1" in
    tests)
      echo "$lsf" | grep -qE '(^|/)(tests?|__tests__|spec|specs)/.*' 2>/dev/null && echo true && return
      echo "$lsf" | grep -qE '\.(test|spec)\.[a-z]+$' 2>/dev/null && echo true && return
      echo false ;;
    ci)
      echo "$lsf" | grep -qE '^\.github/workflows/.*\.ya?ml$' 2>/dev/null && echo true && return
      has_path ".gitlab-ci.yml" && echo true && return
      has_path ".circleci/config.yml" && echo true && return
      echo false ;;
    env_example)
      has_path ".env.example" && echo true && return
      has_path "env.example" && echo true && return
      echo false ;;
    dockerfile)
      has_path "Dockerfile" && echo true && return
      echo "$lsf" | grep -qE '^docker-compose.*\.yml$' 2>/dev/null && echo true && return
      echo false ;;
    health_route)
      hits="$(git_grep '/health' || true)"
      [ -n "$hits" ] && echo true || echo false ;;
    migrations)
      echo "$lsf" | grep -qE '(^|/)(migrations|db/migrations|alembic|prisma)/' 2>/dev/null && echo true && return
      has_path "schema.sql" && echo true && return
      echo false ;;
    i18n)
      echo "$lsf" | grep -qE '(^|/)(locales|l10n|lang|messages)/' 2>/dev/null && echo true && return
      echo "$lsf" | grep -qE '\.arb$' 2>/dev/null && echo true && return
      echo false ;;
    error_tracking)
      manifest_grep="$(git_grep -e 'sentry|bugsnag|rollbar' -- 'package.json' 'requirements*.txt' 'pyproject.toml' 'go.mod' 'Cargo.toml' 'Gemfile' 2>/dev/null)"
      [ -n "$manifest_grep" ] && echo true || echo false ;;
    legal_pages)
      echo "$lsf" | grep -qiE '(^|/)(privacy|terms|privacy-policy|terms-of-service)(\.[a-z]+|\.md)?$' 2>/dev/null && echo true && return
      # routes mention
      hits="$(git_grep -e 'privacy|terms' -- '*.ts' '*.tsx' '*.js' '*.jsx' '*.py' '*.rb' '*.go' 2>/dev/null | head -5)"
      [ -n "$hits" ] && echo true || echo false ;;
    backups)
      echo "$lsf" | grep -qiE '(^|/)(scripts|ops|infra)/.*backup' 2>/dev/null && echo true && return
      echo "$lsf" | grep -qiE 'backup.*\.(sh|ps1|sql)$' 2>/dev/null && echo true && return
      echo false ;;
  esac
}



# stubs count
stubs=0
stub_hits="$(git_grep -e 'TODO|FIXME|NotImplemented' 2>/dev/null || true)"
if [ -n "$stub_hits" ]; then
  stubs="$(echo "$stub_hits" | wc -l | tr -d ' ')"
fi
stubs="${stubs:-0}"

# --- assemble JSON ---------------------------------------------------------
jq -n \
  --arg repo "$REPO" \
  --arg generated_at "$GENERATED_AT" \
  --arg branch "$git_branch" \
  --arg head "$git_head" \
  --argjson dirty "$git_dirty" \
  --argjson prd "$prd_json" \
  --argjson specs "$specs_json" \
  --argjson tests        "$(bool_signal tests)" \
  --argjson ci           "$(bool_signal ci)" \
  --argjson env_example  "$(bool_signal env_example)" \
  --argjson dockerfile   "$(bool_signal dockerfile)" \
  --argjson health_route "$(bool_signal health_route)" \
  --argjson migrations   "$(bool_signal migrations)" \
  --argjson i18n         "$(bool_signal i18n)" \
  --argjson error_tracking "$(bool_signal error_tracking)" \
  --argjson legal_pages  "$(bool_signal legal_pages)" \
  --argjson backups      "$(bool_signal backups)" \
  --argjson stubs        "$stubs" \
  '{
    repo:           $repo,
    generated_at:   $generated_at,
    git:            { branch: $branch, head: $head, dirty: $dirty },
    prd:            $prd,
    specs:          $specs,
    signals: {
      tests:          $tests,
      ci:             $ci,
      env_example:    $env_example,
      dockerfile:     $dockerfile,
      health_route:   $health_route,
      migrations:     $migrations,
      i18n:           $i18n,
      error_tracking: $error_tracking,
      legal_pages:    $legal_pages,
      backups:        $backups,
      stubs:          $stubs
    }
  }'