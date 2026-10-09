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

# --- server mode (FINISH_APPS_SELF=server): local server scan + Mac via `ssh mac` ---
B="$T/bin"; mkdir -p "$B"
cat > "$B/ssh" <<'E'
#!/usr/bin/env bash
# stub ssh: log args, drop options and host, run the remote command locally like a remote shell would
echo "$*" >> "$STUB_LOG"
while [ "${1:-}" = -o ]; do shift 2; done
host="$1"; shift
[ "$host" = mac ] || exit 255
[ -z "${STUB_FAIL:-}" ] || exit 255
eval "$*"
E
chmod +x "$B/ssh"
M="$T/macroots"; mkdir -p "$M"
cp -R "$P/up" "$M/up"                                   # same repo (same root commit) on both hosts
cp -R "$P/up" "$M/up"; git -C "$M/up" commit -q --allow-empty -m macextra
mkdir -p "$M/maconly"; git -C "$M/maconly" init -q -b work; echo m > "$M/maconly/f"
git -C "$M/maconly" add -A; git -C "$M/maconly" commit -q -m c
export STUB_LOG="$T/ssh.log"; : > "$STUB_LOG"
srv() { PATH="$B:$PATH" FINISH_APPS_MAC_SNAPSHOT="${FINISH_APPS_MAC_SNAPSHOT:-$T/none.json}" FINISH_APPS_SELF=server FINISH_APPS_SERVER_ROOTS="$P/*" \
        FINISH_APPS_MAC_ROOTS_REMOTE="$M/*" bash "$SCRIPT" "$@"; }
so="$(srv --host server)"
echo "$so" | jq -e 'length==2 and all(.[]; .host=="server")' >/dev/null \
  || { echo "FAIL server --host server entries"; echo "$so"; fail=1; }
[ ! -s "$STUB_LOG" ] || { echo "FAIL --host server should not ssh"; fail=1; }
so="$(srv --days 7 2>"$T/err")"; rc=$?
[ "$rc" -eq 0 ] || { echo "FAIL server exit=$rc"; fail=1; }
grep -q MyContabo "$STUB_LOG" && { echo "FAIL server mode must not ssh MyContabo"; fail=1; }
grep -q '^-o ConnectTimeout=8 .*mac bash -s -- --scan-local' "$STUB_LOG" || { echo "FAIL ssh mac invocation: $(cat "$STUB_LOG")"; fail=1; }
echo "$so" | jq -e '([.[]|select(.name=="maconly")][0].host)=="mac"' >/dev/null || { echo "FAIL mac entries missing"; echo "$so"; fail=1; }
echo "$so" | jq -e '[.[]|select(.name=="alpha")][0].host=="server"' >/dev/null || { echo "FAIL server entries missing"; fail=1; }
echo "$so" | jq -e '[.[]|select(.name=="up")]|length==1 and (.[0].also_at|length==1) and .[0].host=="mac"' >/dev/null \
  || { echo "FAIL cross-host root-commit dedupe"; echo "$so"; fail=1; }
so="$(STUB_FAIL=1 srv --days 7 2>"$T/err")"; rc=$?
[ "$rc" -eq 0 ] || { echo "FAIL mac-down exit=$rc"; fail=1; }
echo "$so" | jq -e 'length==2 and all(.[]; .host=="server")' >/dev/null || { echo "FAIL mac-down should keep server entries"; fail=1; }
[ "$(grep -ci warn "$T/err")" = 1 ] || { echo "FAIL want exactly one stderr warning"; cat "$T/err"; fail=1; }
: > "$STUB_LOG"
so="$(PATH="$B:$PATH" FINISH_APPS_SELF=mac FINISH_APPS_SSH_HOST= FINISH_APPS_MAC_ROOTS="$P/*" bash "$SCRIPT" --host mac)"
echo "$so" | jq -e 'length==2 and all(.[]; .host=="mac")' >/dev/null || { echo "FAIL SELF=mac unchanged"; fail=1; }
[ ! -s "$STUB_LOG" ] || { echo "FAIL SELF=mac must not call stub ssh"; fail=1; }

# --- server mode with the Mac unreachable: fall back to the pushed snapshot ---
SNAP="$T/mac-latest.json"
FINISH_APPS_SELF=mac FINISH_APPS_SSH_HOST= FINISH_APPS_MAC_ROOTS="$M/*" bash "$SCRIPT" --host mac > "$SNAP"
snap() { STUB_FAIL=1 FINISH_APPS_MAC_SNAPSHOT="$SNAP" srv --days 7 2>"$T/err"; }
so="$(snap)"; rc=$?
[ "$rc" -eq 0 ] || { echo "FAIL snapshot exit=$rc"; fail=1; }
echo "$so" | jq -e '[.[]|select(.name=="maconly")][0]|.host=="mac" and .snapshot==true and (.snapshot_at|test("^[0-9]{4}-[0-9]{2}-[0-9]{2}T"))' >/dev/null   || { echo "FAIL fresh snapshot should add mac entries with snapshot:true"; echo "$so"; fail=1; }
echo "$so" | jq -e '[.[]|select(.name=="up")]|length==1 and (.[0].also_at|length==1) and .[0].snapshot==true' >/dev/null   || { echo "FAIL snapshot entries should dedupe like live ones"; echo "$so"; fail=1; }
echo "$so" | jq -e '[.[]|select(.name=="alpha")][0]|.host=="server" and (has("snapshot")|not)' >/dev/null   || { echo "FAIL server entries must not be marked snapshot"; fail=1; }
touch -t 202001010000 "$SNAP"
so="$(snap)"; rc=$?
[ "$rc" -eq 0 ] || { echo "FAIL stale snapshot exit=$rc"; fail=1; }
echo "$so" | jq -e 'length==2 and all(.[]; .host=="server")' >/dev/null || { echo "FAIL stale snapshot must add no mac entries"; fail=1; }
[ "$(grep -ci warn "$T/err")" -ge 1 ] || { echo "FAIL stale snapshot needs a warning"; fail=1; }
echo '{not json' > "$SNAP"
so="$(snap)"; rc=$?
[ "$rc" -eq 0 ] || { echo "FAIL invalid snapshot exit=$rc"; fail=1; }
echo "$so" | jq -e 'length==2 and all(.[]; .host=="server")' >/dev/null || { echo "FAIL invalid snapshot must add no mac entries"; fail=1; }
[ "$(grep -ci 'warn.*snapshot' "$T/err")" -ge 1 ] || { echo "FAIL invalid snapshot needs a warning"; cat "$T/err"; fail=1; }
rm -f "$SNAP"
so="$(snap)"; rc=$?
[ "$rc" -eq 0 ] && echo "$so" | jq -e 'length==2' >/dev/null || { echo "FAIL missing snapshot"; fail=1; }

[ "$fail" -eq 0 ] && echo "PASS active_test"
exit "$fail"
