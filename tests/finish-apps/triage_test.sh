#!/usr/bin/env bash
# Fixture test for skills/finish-apps/scripts/triage.sh (fake jev via JEV_BIN)
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
SCRIPT="$HERE/../../skills/finish-apps/scripts/triage.sh"
fail=0
command -v jq >/dev/null || { echo "FAIL jq not installed"; exit 1; }
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT

# fake jev: behaviour keyed on the project name inside the --state JSON
cat > "$T/jev" <<'E'
#!/usr/bin/env bash
cmd=$1; shift; state=""
while [ $# -gt 0 ]; do case "$1" in -s|--state) state=$2; shift 2;; *) shift;; esac; done
name=$(printf '%s' "$state" | jq -r .name)
case "$name" in
  broken) exit 2;;
  lowconf) if [ "$cmd" = choice ]; then echo '{"choice":"fix-defects","confidence":0.4}'; exit 2; fi;;
esac
if [ "$cmd" = score ]; then
  case "$name" in beta) echo '{"score":3,"confidence":0.9}';; *) echo '{"score":1,"confidence":0.9}';; esac
else echo '{"choice":"implement-open-tasks","confidence":0.9}'; fi
E
chmod +x "$T/jev"

proj() { # name last_commit customer
  printf '{"name":"%s","host":"mac","path":"/%s","also_at":[],"commits":1,"last_commit":"%s","remote":"","specs_total":1,"specs_missing_plan":0,"specs_missing_tasks":0,"open_tasks":2,"customer":%s}' "$1" "$1" "$2" "$3"
}
{ echo '['; proj alpha 2026-10-08T10:00:00Z false; echo ,; proj beta 2026-10-08T10:00:00Z false; echo ,
  proj up 2026-10-09T10:00:00Z true; echo ,; proj broken 2026-10-01T10:00:00Z false; echo ,
  proj lowconf 2026-10-02T10:00:00Z false; echo ']'; } > "$T/active.json"

out="$(JEV_BIN="$T/jev" bash "$SCRIPT" "$T/active.json")"; rc=$?
[ "$rc" -eq 0 ] || { echo "FAIL exit=$rc"; fail=1; }
echo "$out" | jq -e 'length==5' >/dev/null 2>&1 || { echo "FAIL not 5 entries"; echo "$out"; exit 1; }
g() { echo "$out" | jq -r --arg n "$1" ".[]|select(.name==\$n)|$2"; }
[ "$(g alpha .completeness)" = 1 ] || { echo "FAIL alpha completeness"; fail=1; }
[ "$(g beta .completeness)" = 3 ] || { echo "FAIL beta completeness"; fail=1; }
[ "$(g alpha .next_action)" = implement-open-tasks ] || { echo "FAIL alpha next_action"; fail=1; }
[ "$(g alpha '.report_only // false')" = false ] || { echo "FAIL alpha report_only"; fail=1; }
[ "$(g up .report_only)" = true ] || { echo "FAIL up report_only"; fail=1; }
[ "$(g broken .next_action)" = needs-llm ] || { echo "FAIL exit 2 -> needs-llm"; fail=1; }
[ "$(g lowconf .next_action)" = needs-llm ] || { echo "FAIL low confidence -> needs-llm"; fail=1; }
# sort: last_commit desc, then completeness asc
order="$(echo "$out" | jq -r '[.[].name]|join(",")')"
[ "$order" = "up,alpha,beta,lowconf,broken" ] || { echo "FAIL order got=$order"; fail=1; }

[ "$fail" -eq 0 ] && echo "PASS triage_test"
exit "$fail"
