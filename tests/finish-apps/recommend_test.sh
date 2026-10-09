#!/usr/bin/env bash
# Fixture test for skills/finish-apps/scripts/recommend.sh (fake LLM via FINISH_APPS_LLM, fake jev via JEV_BIN)
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
SCRIPT="$HERE/../../skills/finish-apps/scripts/recommend.sh"
fail=0
command -v jq >/dev/null || { echo "FAIL jq not installed"; exit 1; }
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT

mkrepo() { # dir
  mkdir -p "$1/specs/001-core" "$1/specs/002-extra"
  touch "$1/specs/001-core/spec.md" "$1/specs/001-core/plan.md" "$1/specs/002-extra/spec.md"
  printf -- '- [ ] one\n- [x] two\n' > "$1/specs/001-core/tasks.md"
  echo "# PRD" > "$1/PRD.md"; echo "// TODO fix" > "$1/app.js"
  git -C "$1" init -q && git -C "$1" add -A && git -C "$1" -c user.email=t@t -c user.name=t commit -qm init
}
mkrepo "$T/alpha"; mkrepo "$T/badllm"; mkrepo "$T/up"

# fake LLM: output depends on the project name in the prompt
cat > "$T/llm" <<'E2'
#!/usr/bin/env bash
p="$(cat)"
case "$p" in
  *"PROJECT: badllm"*) echo "this is not json"; exit 0;;
esac
cat <<'J'
```json
[
 {"title":"Fix crash","kind":"fix-defects","why":"Crashes.","evidence":["app.js"],"size":"L"},
 {"title":"Add search","kind":"new-feature","why":"Users need it.","evidence":["PRD.md"],"size":"S"},
 {"title":"Finish extra","kind":"complete-spec","why":"No plan.","evidence":["specs/002-extra"],"size":"M"},
 {"title":"Dup of core","kind":"new-feature","why":"Same.","evidence":["specs/001-core"],"size":"S"},
 {"title":"Ghost","kind":"polish","why":"x","evidence":["nope/missing.md"],"size":"S"},
 {"title":"Unknown impact","kind":"research","why":"y","evidence":["PRD.md"],"size":"S"}
]
J
E2
chmod +x "$T/llm"

cat > "$T/jev" <<'E2'
#!/usr/bin/env bash
cmd=$1; shift; state=""
while [ $# -gt 0 ]; do case "$1" in -s|--state) state=$2; shift 2;; *) shift;; esac; done
title=$(printf '%s' "$state" | jq -r '.title // .candidate.title')
case "$cmd" in
  score) case "$title" in
    "Fix crash") echo '{"score":4,"confidence":0.9}';;
    "Add search"|"Finish extra") echo '{"score":3,"confidence":0.9}';;
    "Unknown impact") exit 2;;
    *) echo '{"score":2,"confidence":0.9}';; esac;;
  noul) case "$title" in "Dup of core") echo '{"noul":0.9}';; *) echo '{"noul":0.1}';; esac;;
esac
E2
chmod +x "$T/jev"

cat > "$T/in.json" <<J
[{"name":"alpha","host":"mac","path":"$T/alpha"},
 {"name":"badllm","host":"mac","path":"$T/badllm"},
 {"name":"remote","host":"server","path":"/nonexistent/remote"},
 {"name":"up","host":"mac","path":"$T/up","customer":true,"report_only":true}]
J

out="$(FINISH_APPS_LLM="$T/llm" JEV_BIN="$T/jev" bash "$SCRIPT" "$T/in.json" --top 5)"; rc=$?
[ "$rc" -eq 0 ] || { echo "FAIL exit=$rc"; fail=1; }
echo "$out" | jq -e 'length==4' >/dev/null 2>&1 || { echo "FAIL not 4 entries"; echo "$out"; exit 1; }
g() { echo "$out" | jq -r --arg n "$1" ".[]|select(.name==\$n)|$2"; }
[ "$(g alpha '[.recommendations[].title]|join(",")')" = "Fix crash,Add search,Finish extra,Unknown impact" ] || { echo "FAIL order: $(g alpha '[.recommendations[].title]|join(",")')"; fail=1; }
[ "$(g alpha '[.recommendations[].code]|join(",")')" = "R1,R2,R3,R4" ] || { echo "FAIL codes"; fail=1; }
[ "$(g alpha '.recommendations[3].impact')" = null ] || { echo "FAIL exit 2 impact not null"; fail=1; }
[ "$(g alpha '.recommendations[0].impact')" = 4 ] || { echo "FAIL impact"; fail=1; }
[ "$(g alpha '.recommendations[0]|has("impact_confidence") and has("evidence") and has("size") and has("kind") and has("why")')" = true ] || { echo "FAIL fields"; fail=1; }
[ "$(g alpha '.report_only // false')" = false ] || { echo "FAIL alpha report_only"; fail=1; }
[ "$(g badllm '.recommendations|length')" = 0 ] || { echo "FAIL badllm recs"; fail=1; }
[ "$(g badllm '.error|length>0')" = true ] || { echo "FAIL badllm error"; fail=1; }
[ "$(g remote .skipped)" = other-host ] || { echo "FAIL other-host"; fail=1; }
[ "$(g up .report_only)" = true ] || { echo "FAIL customer report_only"; fail=1; }
top3="$(FINISH_APPS_LLM="$T/llm" JEV_BIN="$T/jev" bash "$SCRIPT" "$T/in.json" | jq -r '.[]|select(.name=="alpha")|.recommendations|length')"
[ "$top3" = 3 ] || { echo "FAIL default top is 3, got $top3"; fail=1; }

[ "$fail" -eq 0 ] && echo "PASS recommend_test"
exit "$fail"
