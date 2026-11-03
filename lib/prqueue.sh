#!/usr/bin/env bash
# lib/prqueue.sh — PR queue and ticket-state helpers for spec-002-factory-flow (R1, R2, R9)

_prqueue_root() {
  cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd
}

_prqueue_load_config() {
  local cfg="${FACTORY_CONFIG:-$(_prqueue_root)/config/factory.env}"
  if [ -f "$cfg" ]; then
    # shellcheck disable=SC1090
    source "$cfg"
  fi
  FACTORY_WIP_LIMIT="${FACTORY_WIP_LIMIT:-3}"
  FACTORY_REPOS="${FACTORY_REPOS:-}"
  FACTORY_AUTOMERGE_REPOS="${FACTORY_AUTOMERGE_REPOS:-}"
}

# Resolve a project name (e.g. "mediatgb") or owner/repo string to "owner/repo".
prqueue_repo_for() {
  local proj="${1:-}"
  _prqueue_load_config
  if [[ "$proj" == */* ]]; then
    echo "$proj"
    return 0
  fi
  local p_low
  p_low=$(printf "%s" "$proj" | tr "[:upper:]" "[:lower:]")
  local entry k v
  for entry in $FACTORY_REPOS; do
    k=$(printf "%s" "${entry%%=*}" | tr "[:upper:]" "[:lower:]")
    v="${entry#*=}"
    if [ "$k" = "$p_low" ] && [ -n "$v" ]; then
      echo "$v"
      return 0
    fi
  done
  return 1
}

# Return 0 if project/repo is enabled for GitHub auto-merge (R2, R9), 1 otherwise.
prqueue_is_automerge() {
  local repo
  repo=$(prqueue_repo_for "${1:-}") || return 1
  _prqueue_load_config
  local r_low item
  r_low=$(printf "%s" "$repo" | tr "[:upper:]" "[:lower:]")
  for item in $FACTORY_AUTOMERGE_REPOS; do
    if [ "$(printf "%s" "$item" | tr "[:upper:]" "[:lower:]")" = "$r_low" ]; then
      return 0
    fi
  done
  return 1
}

# Derive ticket state from a PR JSON object (R2):
# building -> ready -> merged -> deploy-offered -> deployed
prqueue_ticket_state() {
  local json="${1:-}"
  python3 -c '
import json, sys
try:
    d = json.loads(sys.argv[1])
except Exception:
    print("unknown")
    sys.exit(0)
state = str(d.get("state") or "").upper()
if state == "MERGED":
    if d.get("deployed"):
        print("deployed")
    elif d.get("deployOffered"):
        print("deploy-offered")
    else:
        print("merged")
elif state == "OPEN":
    if d.get("autoMergeRequest") and not d.get("isDraft"):
        print("ready")
    else:
        print("building")
else:
    print(state.lower() or "unknown")
' "$json"
}

# List open PRs waiting on auto-merge (state=ready) as a JSON array.
prqueue_list_waiting() {
  local repo
  repo=$(prqueue_repo_for "${1:-}") || { echo "[]"; return 0; }
  local raw
  raw=$(gh pr list -R "$repo" --state open --limit 100 --json number,state,isDraft,autoMergeRequest,headRefName 2>/dev/null) || return 1
  python3 -c '
import json, sys
try:
    prs = json.loads(sys.argv[1])
except Exception:
    sys.exit(1)
waiting = [p for p in prs if isinstance(p, dict) and not p.get("isDraft") and p.get("autoMergeRequest")]
print(json.dumps(waiting))
' "$raw"
}

# Count open PRs waiting on auto-merge for project/repo (R1).
prqueue_waiting_count() {
  local waiting
  waiting=$(prqueue_list_waiting "${1:-}") || { echo "unknown"; return 0; }
  python3 -c '
import json, sys
try:
    prs = json.loads(sys.argv[1])
    print(len(prs) if isinstance(prs, list) else 0)
except Exception:
    print("unknown")
' "$waiting"
}

# Arm GitHub auto-merge (--auto --squash) for an open non-draft PR on branch (or PR number) when repo is in auto-merge (R2).
prqueue_arm_automerge() {
  local proj="${1:-}" ref="${2:-}"
  [ -n "$proj" ] && [ -n "$ref" ] || return 1
  prqueue_is_automerge "$proj" || return 1
  local repo
  repo=$(prqueue_repo_for "$proj") || return 1
  local pr_num="$ref"
  if ! [[ "$ref" =~ ^[0-9]+$ ]]; then
    local raw
    raw=$(gh pr list -R "$repo" --head "$ref" --state open --json number,isDraft,autoMergeRequest 2>/dev/null) || { echo "prqueue: gh pr list failed for $repo $ref" >&2; return 1; }
    pr_num=$(python3 -c '
import json, sys
try:
    prs = json.loads(sys.argv[1])
    for p in prs:
        if isinstance(p, dict) and not p.get("isDraft"):
            print(p.get("number", ""))
            break
except Exception:
    pass
' "$raw")
  fi
  [ -n "$pr_num" ] || { echo "prqueue: no open PR found for $repo $ref" >&2; return 1; }
  # only arm when ci-ok is a required check, else --auto merges immediately
  gh api "repos/$repo/branches/main/protection/required_status_checks" --jq '.contexts[]?, .checks[]?.context' 2>/dev/null | grep -qx 'ci-ok' \
    || { echo "prqueue: ci-ok not required on $repo main; not arming" >&2; return 1; }
  gh pr merge "$pr_num" -R "$repo" --auto --squash >/dev/null || return 1
  return 0
}
