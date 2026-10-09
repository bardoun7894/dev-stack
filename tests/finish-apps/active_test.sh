#!/usr/bin/env bash
# Fixture test for skills/finish-apps/scripts/active.sh
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
SCRIPT="$HERE/../../skills/finish-apps/scripts/active.sh"
fail=0
command -v jq >/dev/null || { echo "FAIL jq not installed"; exit 1; }

T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
P="$T/projects"; mkdir -p "$P"
export GIT_AUTHOR_NAME=Test GIT_AUTHOR_EMAIL=t@e.com GIT_COMMITTER_NAME=Test GIT_COMMITTER_EMAIL=t@e.com

mkrepo() { # name [date]
  mkdir -p "$P/$1"; git -C "$P/$1" init -q -b work
  echo "$1" > "$P/$1/f"; git -C "$P/$1" add -A
  if [ -n "${2:-}" ]; then GIT_COMMITTER_DATE="$2" GIT_AUTHOR_DATE="$2" git -C "$P/$1" commit -q -m c
  else git -C "$P/$1" commit -q -m c; fi
}

mkrepo alpha
git -C "$P/alpha" remote add origin git@github.com:Owner/Alpha.git
mkdir -p "$P/alpha/specs/001-a" "$P/alpha/specs/002-b" "$P/alpha/specs/003-c"
echo s > "$P/alpha/specs/001-a/spec.md"; echo p > "$P/alpha/specs/001-a/plan.md"
printf -- '- [ ] one\n- [ ] two\n- [x] three\n' > "$P/alpha/specs/001-a/tasks.md"
echo s > "$P/alpha/specs/002-b/spec.md"; echo p > "$P/alpha/specs/002-b/plan.md"   # no tasks.md
echo s > "$P/alpha/specs/003-c/spec.md"                                            # no plan, no tasks
git -C "$P/alpha" add -A; git -C "$P/alpha" commit -q -m specs
mkrepo oldie "2020-01-01T00:00:00"
mkrepo up
git -C "$P/alpha" worktree add -q "$P/alpha-wt" -b side
echo y > "$P/alpha-wt/g"; git -C "$P/alpha-wt" add -A; git -C "$P/alpha-wt" commit -q -m wt
mkdir -p "$P/notrepo"

run() { FINISH_APPS_SSH_HOST= FINISH_APPS_MAC_ROOTS="$P/*" bash "$SCRIPT" "$@"; }
out="$(run --host mac)"; rc=$?
[ "$rc" -eq 0 ] || { echo "FAIL exit=$rc"; fail=1; }
echo "$out" | jq -e 'type=="array"' >/dev/null 2>&1 || { echo "FAIL not a JSON array"; echo "$out"; exit 1; }

names="$(echo "$out" | jq -r '[.[].name]|sort|join(",")')"
[ "$names" = "alpha,up" ] || { echo "FAIL names want=alpha,up got=$names"; fail=1; }
g() { echo "$out" | jq -r --arg n "$1" ".[]|select(.name==\$n)|$2"; }
[ "$(g alpha .specs_total)" = 3 ] || { echo "FAIL specs_total"; fail=1; }
[ "$(g alpha .specs_missing_plan)" = 1 ] || { echo "FAIL specs_missing_plan"; fail=1; }
[ "$(g alpha .specs_missing_tasks)" = 2 ] || { echo "FAIL specs_missing_tasks"; fail=1; }
[ "$(g alpha .open_tasks)" = 2 ] || { echo "FAIL open_tasks"; fail=1; }
# --all counts the shared-object branch commit too: init + specs + wt = 3
[ "$(g alpha .commits)" = 3 ] || { echo "FAIL commits want 3 got $(g alpha .commits)"; fail=1; }
[ "$(g alpha .host)" = mac ] || { echo "FAIL host"; fail=1; }
[ "$(g alpha .customer)" = false ] || { echo "FAIL alpha customer"; fail=1; }
[ "$(g up .customer)" = true ] || { echo "FAIL up customer"; fail=1; }
[ "$(g alpha .remote)" = "github.com/owner/alpha" ] || { echo "FAIL remote got=$(g alpha .remote)"; fail=1; }
echo "$out" | jq -e '.[0]|has("also_at") and has("last_commit") and has("path")' >/dev/null || { echo "FAIL fields"; fail=1; }

# window: a large --days brings oldie in
n="$(run --host mac --days 5000 | jq '[.[].name]|index("oldie")!=null')"
[ "$n" = true ] || { echo "FAIL --days 5000 should include oldie"; fail=1; }

# dedupe by remote: a second clone with more commits wins, the other path goes to also_at
mkdir -p "$T/srv"; cp -R "$P/alpha" "$T/srv/alpha"
git -C "$T/srv/alpha" worktree prune
git -C "$T/srv/alpha" commit -q --allow-empty -m extra
d="$(FINISH_APPS_SSH_HOST= FINISH_APPS_MAC_ROOTS="$P/* $T/srv/*" bash "$SCRIPT" --host mac)"
echo "$d" | jq -e '[.[]|select(.name=="alpha")]|length==1 and (.[0].also_at|length==1) and .[0].path=="'"$T"'/srv/alpha"' >/dev/null \
  || { echo "FAIL remote dedupe keeps most commits"; echo "$d"; fail=1; }

# dedupe by root commit: copies with different or no remotes, including same-host paths
mkdir -p "$T/a2" "$T/a3"; cp -R "$P/up" "$T/a2/up"; cp -R "$P/up" "$T/a3/up"
git -C "$T/a2/up" remote add origin git@github.com:one/up.git
git -C "$T/a3/up" remote add origin git@github.com:two/up.git
r="$(FINISH_APPS_SSH_HOST= FINISH_APPS_MAC_ROOTS="$P/up $T/a2/* $T/a3/*" bash "$SCRIPT" --host mac)"
echo "$r" | jq -e '[.[]|select(.name=="up")]|length==1 and (.[0].also_at|length==2) and (.[0].root_commit|length==40)' >/dev/null \
  || { echo "FAIL root-commit dedupe across differing remotes"; echo "$r"; fail=1; }
r="$(FINISH_APPS_SSH_HOST= FINISH_APPS_MAC_ROOTS="$P/up $T/a3/*" bash "$SCRIPT" --host mac)"
echo "$r" | jq -e '[.[]|select(.name=="up")]|length==1 and (.[0].also_at|length==1) and (.[0].root_commit|length==40)' >/dev/null \
  || { echo "FAIL root-commit dedupe no-remote vs remote"; echo "$r"; fail=1; }

# unreachable server warns and continues with mac results
w="$(FINISH_APPS_SSH_HOST=nonexistent.invalid FINISH_APPS_MAC_ROOTS="$P/*" bash "$SCRIPT" 2>"$T/err")"
echo "$w" | jq -e 'length==2' >/dev/null || { echo "FAIL unreachable server should still give mac results"; fail=1; }
grep -qi warn "$T/err" || { echo "FAIL no warning on stderr"; fail=1; }

[ "$fail" -eq 0 ] && echo "PASS active_test"
exit "$fail"
