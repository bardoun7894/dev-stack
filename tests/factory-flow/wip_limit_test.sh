#!/usr/bin/env bash
# wip_limit_test.sh — test R1 (F5): jdelegate refuses a new build worker when project P has >= N open PRs waiting on auto-merge,
# and accepts when count drops below N. Reviewer/verify/researcher runs are exempt.
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/../.." && pwd)
JD="$ROOT/bin/jdelegate"
PRQ="$ROOT/lib/prqueue.sh"

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

REPO="$TMP/mediatgb"
mkdir -p "$REPO"
git -C "$REPO" init -q
git -C "$REPO" remote add github https://github.com/bardoun7894/mediatgb.git

BIN="$TMP/bin"
mkdir -p "$BIN"

cat <<'STUB' > "$BIN/jev"
#!/usr/bin/env bash
exit 3
STUB
chmod +x "$BIN/jev"

PR_STATE_FILE="$TMP/prs.json"
cat <<'STUB' > "$BIN/gh"
#!/usr/bin/env bash
if [[ "$*" == *"pr list"* ]]; then
  cat "$PR_STATE_FILE"
  exit 0
fi
exit 0
STUB
chmod +x "$BIN/gh"

TIERS="$TMP/tiers.json"
echo '{"tiers":{"T0":["cliproxy/claude-test"],"T1":["cliproxy/claude-test"],"T2":["cliproxy/claude-test"],"T3":["cliproxy/claude-test"],"T4":["cliproxy/claude-test"]}}' > "$TIERS"

FACTORY_ENV="$TMP/factory.env"
cat <<EOF2 > "$FACTORY_ENV"
FACTORY_WIP_LIMIT=3
FACTORY_REPOS="mediatgb=bardoun7894/mediatgb"
FACTORY_AUTOMERGE_REPOS="bardoun7894/mediatgb"
EOF2

run_jd() {
  PR_STATE_FILE="$PR_STATE_FILE" PATH="$BIN:$PATH" JDELEGATE_JEV="$BIN/jev" JEV_ROUTER_CONFIG="$TIERS" \
    JDELEGATE_CACHE="$TMP/cache" JDELEGATE_AUTO_SKILL=0 JDELEGATE_AUTO_ROLE=0 JDELEGATE_AUTO_MCP=0 \
    JDELEGATE_SELECT_CACHE=0 JDELEGATE_KB=0 FACTORY_CONFIG="$FACTORY_ENV" \
    node "$JD" --dry-run --harness claude --cwd "$REPO" "$@" "implement feature X" 2>&1
}

# 1. N=3 open PRs with autoMergeRequest non-null -> prqueue_waiting_count returns 3, jdelegate refuses build worker (exit != 0)
cat <<'JSON' > "$PR_STATE_FILE"
[
  {"number":101,"state":"OPEN","isDraft":false,"autoMergeRequest":{"enabledAt":"2026-11-03T00:00:00Z"},"headRefName":"b1"},
  {"number":102,"state":"OPEN","isDraft":false,"autoMergeRequest":{"enabledAt":"2026-11-03T00:01:00Z"},"headRefName":"b2"},
  {"number":103,"state":"OPEN","isDraft":false,"autoMergeRequest":{"enabledAt":"2026-11-03T00:02:00Z"},"headRefName":"b3"}
]
JSON

[ -f "$PRQ" ] || { echo "FAIL: $PRQ missing"; exit 1; }
# shellcheck disable=SC1090
source "$PRQ"
CNT=$(PR_STATE_FILE="$PR_STATE_FILE" PATH="$BIN:$PATH" FACTORY_CONFIG="$FACTORY_ENV" prqueue_waiting_count "mediatgb")
[ "$CNT" = "3" ] || { echo "FAIL: expected waiting count 3, got $CNT"; exit 1; }

set +e
OUT=$(run_jd --name build-w1)
RC=$?
set -e
[ "$RC" -ne 0 ] || { echo "FAIL: expected jdelegate to refuse at N=3, but exited 0"; exit 1; }
echo "$OUT" | grep -qE "3.*auto-merge|waiting on auto-merge" || { echo "FAIL: refusal message did not name the count: $OUT"; exit 1; }

# Reviewer is exempt even at N=3
OUT_REV=$(run_jd --name review-w1 --role reviewer)
echo "$OUT_REV" | grep -q "dry-run" || { echo "FAIL: reviewer should not be refused by WIP limit: $OUT_REV"; exit 1; }

# 2. Drop to 2 PRs waiting on auto-merge (one has autoMergeRequest: null) -> accepted
cat <<'JSON' > "$PR_STATE_FILE"
[
  {"number":101,"state":"OPEN","isDraft":false,"autoMergeRequest":{"enabledAt":"2026-11-03T00:00:00Z"},"headRefName":"b1"},
  {"number":102,"state":"OPEN","isDraft":false,"autoMergeRequest":{"enabledAt":"2026-11-03T00:01:00Z"},"headRefName":"b2"},
  {"number":103,"state":"OPEN","isDraft":false,"autoMergeRequest":null,"headRefName":"b3"}
]
JSON

CNT2=$(PR_STATE_FILE="$PR_STATE_FILE" PATH="$BIN:$PATH" FACTORY_CONFIG="$FACTORY_ENV" prqueue_waiting_count "mediatgb")
[ "$CNT2" = "2" ] || { echo "FAIL: expected waiting count 2, got $CNT2"; exit 1; }

OUT2=$(run_jd --name build-w2)
echo "$OUT2" | grep -q "dry-run" || { echo "FAIL: expected jdelegate to accept at count=2: $OUT2"; exit 1; }

echo "PASS: wip_limit_test.sh"
