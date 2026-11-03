#!/usr/bin/env bash
# automerge_test.sh — test R2, R9 (F1, F15, F16):
# - F1: ticket states (building -> ready -> merged -> deploy-offered -> deployed) derived from PR state,
#       and implementer exit arms `gh pr merge --auto --squash` on an auto-merge repo.
# - F15: repo without ci-ok stays out of auto-merge; joins once ci-ok is present.
# - F16: bin/merge-fallback runs under gate-run <project>-merge with <=90m timeout cap.
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/../.." && pwd)
PRQ="$ROOT/lib/prqueue.sh"
FB="$ROOT/bin/merge-fallback"

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

[ -f "$PRQ" ] || { echo "FAIL: $PRQ missing"; exit 1; }
# shellcheck disable=SC1090
source "$PRQ"

# 1. Ticket state derivation (R2 / F1)
S1=$(prqueue_ticket_state '{"state":"OPEN","isDraft":true,"autoMergeRequest":null}')
[ "$S1" = "building" ] || { echo "FAIL: draft open PR should be building, got $S1"; exit 1; }

S2=$(prqueue_ticket_state '{"state":"OPEN","isDraft":false,"autoMergeRequest":{"enabledAt":"2026-11-03T00:00:00Z"}}')
[ "$S2" = "ready" ] || { echo "FAIL: open PR with autoMergeRequest should be ready, got $S2"; exit 1; }

S3=$(prqueue_ticket_state '{"state":"MERGED","mergedAt":"2026-11-03T01:00:00Z"}')
[ "$S3" = "merged" ] || { echo "FAIL: merged PR should be merged, got $S3"; exit 1; }

S4=$(prqueue_ticket_state '{"state":"MERGED","mergedAt":"2026-11-03T01:00:00Z","deployOffered":true}')
[ "$S4" = "deploy-offered" ] || { echo "FAIL: merged PR with deployOffered should be deploy-offered, got $S4"; exit 1; }

S5=$(prqueue_ticket_state '{"state":"MERGED","mergedAt":"2026-11-03T01:00:00Z","deployed":true}')
[ "$S5" = "deployed" ] || { echo "FAIL: merged PR with deployed should be deployed, got $S5"; exit 1; }

# 2. F15: Repo without ci-ok stays out of auto-merge; repo with ci-ok joins auto-merge
BIN="$TMP/bin"
mkdir -p "$BIN"
GH_LOG="$TMP/gh.log"
STUB_CHECKS_FILE="$TMP/checks.txt"
printf "ci-ok\n" > "$STUB_CHECKS_FILE"

cat <<'STUB' > "$BIN/gh"
#!/usr/bin/env bash
echo "gh $*" >> "$GH_LOG"
if [[ "$*" == *"api repos/"*"required_status_checks"* ]]; then
  cat "$STUB_CHECKS_FILE"
  exit 0
fi
if [[ "$*" == *"pr view"* ]] || [[ "$*" == *"pr list"* ]]; then
  echo '[{"number":42,"state":"OPEN","isDraft":false,"autoMergeRequest":null,"headRefName":"feat-x","baseRefName":"main"}]'
  exit 0
fi
exit 0
STUB
chmod +x "$BIN/gh"

FACTORY_ENV="$TMP/factory.env"
cat <<EOF2 > "$FACTORY_ENV"
FACTORY_WIP_LIMIT=3
FACTORY_REPOS="mediatgb=bardoun7894/mediatgb crmai=bardoun7894/crmAi"
FACTORY_AUTOMERGE_REPOS="bardoun7894/mediatgb"
EOF2

if STUB_CHECKS_FILE="$STUB_CHECKS_FILE" GH_LOG="$GH_LOG" PATH="$BIN:$PATH" FACTORY_CONFIG="$FACTORY_ENV" prqueue_is_automerge "crmai"; then
  echo "FAIL: crmai without ci-ok should not be in auto-merge"
  exit 1
fi
if ! STUB_CHECKS_FILE="$STUB_CHECKS_FILE" GH_LOG="$GH_LOG" PATH="$BIN:$PATH" FACTORY_CONFIG="$FACTORY_ENV" prqueue_is_automerge "mediatgb"; then
  echo "FAIL: mediatgb should be in auto-merge"
  exit 1
fi

# 3. F1 & F15: arming auto-merge succeeds when ci-ok is required, and refuses when ci-ok is missing
: > "$GH_LOG"
STUB_CHECKS_FILE="$STUB_CHECKS_FILE" GH_LOG="$GH_LOG" PATH="$BIN:$PATH" FACTORY_CONFIG="$FACTORY_ENV" prqueue_arm_automerge "mediatgb" "feat-x"
grep -q "pr merge 42 -R bardoun7894/mediatgb --auto --squash" "$GH_LOG" || { echo "FAIL: prqueue_arm_automerge did not run gh pr merge --auto --squash: $(cat "$GH_LOG")"; exit 1; }

: > "$GH_LOG"
: > "$STUB_CHECKS_FILE"
set +e
STUB_CHECKS_FILE="$STUB_CHECKS_FILE" GH_LOG="$GH_LOG" PATH="$BIN:$PATH" FACTORY_CONFIG="$FACTORY_ENV" prqueue_arm_automerge "mediatgb" "feat-x" 2>/dev/null
RC_NOCI=$?
set -e
[ "$RC_NOCI" -ne 0 ] || { echo "FAIL: prqueue_arm_automerge should refuse when ci-ok is missing from required_status_checks"; exit 1; }
if grep -q "pr merge" "$GH_LOG"; then
  echo "FAIL: prqueue_arm_automerge called pr merge without ci-ok"
  exit 1
fi

# 4. F16: bin/merge-fallback uses gate-run <project>-merge with <=90m timeout
[ -x "$FB" ] || { echo "FAIL: $FB missing or not executable"; exit 1; }
GATE_LOG="$TMP/gate.log"
cat <<'STUB' > "$BIN/gate-run"
#!/usr/bin/env bash
echo "gate-run $*" >> "$GATE_LOG"
shift 3
"$@"
STUB
chmod +x "$BIN/gate-run"

GATE_LOG="$GATE_LOG" PATH="$BIN:$PATH" "$FB" mediatgb 60m -- echo "merged-ok" >/dev/null
grep -q "gate-run mediatgb-merge 60m -- echo merged-ok" "$GATE_LOG" || { echo "FAIL: merge-fallback did not invoke gate-run mediatgb-merge: $(cat "$GATE_LOG")"; exit 1; }

set +e
GATE_LOG="$GATE_LOG" PATH="$BIN:$PATH" "$FB" mediatgb 120m -- echo "too-long" >/dev/null 2>&1
RC_LONG=$?
GATE_LOG="$GATE_LOG" PATH="$BIN:$PATH" "$FB" mediatgb 5x -- echo "bad-unit" >/dev/null 2>&1
RC_BAD=$?
set -e
[ "$RC_LONG" -ne 0 ] || { echo "FAIL: merge-fallback should refuse timeout > 90m"; exit 1; }
[ "$RC_BAD" -ne 0 ] || { echo "FAIL: merge-fallback should refuse invalid timeout unit"; exit 1; }

# 5. F1: jdelegate dry-run script for a build worker includes prqueue_arm_automerge on exit 0
REPO="$TMP/mediatgb"
mkdir -p "$REPO"
git -C "$REPO" init -q
cat <<'STUB' > "$BIN/jev"
#!/usr/bin/env bash
exit 3
STUB
chmod +x "$BIN/jev"
TIERS="$TMP/tiers.json"
echo '{"tiers":{"T0":["cliproxy/claude-test"],"T1":["cliproxy/claude-test"],"T2":["cliproxy/claude-test"],"T3":["cliproxy/claude-test"],"T4":["cliproxy/claude-test"]}}' > "$TIERS"
OUT_JD=$(STUB_CHECKS_FILE="$STUB_CHECKS_FILE" GH_LOG="$GH_LOG" PATH="$BIN:$PATH" JDELEGATE_JEV="$BIN/jev" JEV_ROUTER_CONFIG="$TIERS" \
  JDELEGATE_CACHE="$TMP/cache" JDELEGATE_AUTO_SKILL=0 JDELEGATE_AUTO_ROLE=0 JDELEGATE_AUTO_MCP=0 \
  JDELEGATE_SELECT_CACHE=0 JDELEGATE_KB=0 FACTORY_CONFIG="$FACTORY_ENV" \
  node "$ROOT/bin/jdelegate" --dry-run --harness claude --cwd "$REPO" --name build-arm "implement feature Y" 2>&1 || true)
echo "$OUT_JD" | grep -q "prqueue_arm_automerge" || { echo "FAIL: jdelegate run.sh missing prqueue_arm_automerge: $OUT_JD"; exit 1; }

echo "PASS: automerge_test.sh"
