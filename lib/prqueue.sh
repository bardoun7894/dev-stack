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

# Resolve a directory path, project name (e.g. "mediatgb") or owner/repo string to "owner/repo".
prqueue_repo_for() {
  local proj="${1:-}"
  _prqueue_load_config
  if [ -d "$proj" ]; then
    local url
    url=$(git -C "$proj" remote get-url github 2>/dev/null || git -C "$proj" remote get-url origin 2>/dev/null || true)
    if [[ "$url" =~ github\.com[:/]([^/]+/[^/]+)$ ]]; then
      local m="${BASH_REMATCH[1]}"
      echo "${m%.git}"
      return 0
    fi
    proj=$(basename "$proj")
  fi
  if [[ "$proj" == */* ]]; then
    echo "${proj%.git}"
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
# Note: deployOffered and deployed are supplied by the Tokyo deploy registry (or labels "deploy-offered" / "deployed").
prqueue_ticket_state() {
  local json="${1:-}"
  printf "%s" "$json" | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
except Exception:
    print("unknown")
    sys.exit(0)
state = str(d.get("state") or "").upper()
labels = [str(x.get("name") if isinstance(x, dict) else x).lower() for x in (d.get("labels") or [])]
if state == "MERGED":
    if d.get("deployed") or "deployed" in labels:
        print("deployed")
    elif d.get("deployOffered") or "deploy-offered" in labels:
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
'
}

# List open PRs waiting on auto-merge (state=ready) as a JSON array.
prqueue_list_waiting() {
  local repo
  repo=$(prqueue_repo_for "${1:-}") || { echo "[]"; return 0; }
  local raw
  raw=$(timeout 15 gh pr list -R "$repo" --state open --limit 1000 --json number,state,isDraft,autoMergeRequest,headRefName,baseRefName,labels 2>/dev/null) || return 1
  printf "%s" "$raw" | python3 -c '
import json, sys
try:
    prs = json.load(sys.stdin)
except Exception:
    sys.exit(1)
waiting = [p for p in prs if isinstance(p, dict) and not p.get("isDraft") and p.get("autoMergeRequest")]
print(json.dumps(waiting))
'
}

# Count open PRs waiting on auto-merge for project/repo (R1).
prqueue_waiting_count() {
  local waiting
  waiting=$(prqueue_list_waiting "${1:-}") || { echo "unknown"; return 0; }
  printf "%s" "$waiting" | python3 -c '
import json, sys
try:
    prs = json.load(sys.stdin)
    print(len(prs) if isinstance(prs, list) else 0)
except Exception:
    print("unknown")
'
}

# Arm GitHub auto-merge (--auto --squash) for an open non-draft PR on branch (or PR number) when repo is in auto-merge (R2).
# Gated by both required check `ci-ok` on main AND a passing `pr-review` verdict (status context `pr-review` or two `VERDICT: PASS` sections in `<!-- haiku-review sha=<head> -->`).
prqueue_arm_automerge() {
  local proj="${1:-}" ref="${2:-}"
  [ -n "$proj" ] && [ -n "$ref" ] || return 1
  prqueue_is_automerge "$proj" || return 1
  local repo
  repo=$(prqueue_repo_for "$proj") || return 1
  local raw
  if [[ "$ref" =~ ^[0-9]+$ ]]; then
    raw=$(timeout 15 gh pr view "$ref" -R "$repo" --json number,isDraft,baseRefName,headRefOid,comments,reviews,statusCheckRollup 2>/dev/null) || { echo "prqueue: gh pr view failed for $repo #$ref" >&2; return 1; }
    raw="[$raw]"
  else
    raw=$(timeout 15 gh pr list -R "$repo" --head "$ref" --state open --json number,isDraft,baseRefName,headRefOid,comments,reviews,statusCheckRollup 2>/dev/null) || { echo "prqueue: gh pr list failed for $repo $ref" >&2; return 1; }
  fi
  local parsed
  parsed=$(printf "%s" "$raw" | python3 -c '
import json, re, sys
try:
    prs = json.load(sys.stdin)
except Exception:
    sys.exit(1)
for p in (prs if isinstance(prs, list) else []):
    if not isinstance(p, dict) or p.get("isDraft"):
        continue
    num = p.get("number", "")
    base = p.get("baseRefName", "main")
    sha = str(p.get("headRefOid") or "")
    verdict_ok = False
    for sc in (p.get("statusCheckRollup") or []):
        if isinstance(sc, dict) and sc.get("context") == "pr-review" and str(sc.get("state") or "").upper() == "SUCCESS":
            verdict_ok = True
        if isinstance(sc, dict) and sc.get("name") == "pr-review" and str(sc.get("conclusion") or "").upper() == "SUCCESS":
            verdict_ok = True
    if sha and not verdict_ok:
        marker = f"<!-- haiku-review sha={sha} -->"
        bodies = [str(x.get("body") or "") for x in (p.get("comments") or []) + (p.get("reviews") or []) if isinstance(x, dict) and marker in str(x.get("body") or "")]
        if bodies:
            last = bodies[-1]
            verdicts = re.findall(r"^\s*VERDICT:\s*(PASS|BLOCK)\s*$", last, re.M)
            if len(verdicts) >= 2 and all(v == "PASS" for v in verdicts):
                verdict_ok = True
    print(f"{num} {base} {1 if verdict_ok else 0}")
    break
') || parsed=""
  local pr_num base_branch verdict_ok
  read -r pr_num base_branch verdict_ok <<< "$parsed"
  [ -n "$pr_num" ] || { echo "prqueue: no open non-draft PR found for $repo $ref" >&2; return 1; }
  [ "$base_branch" = "main" ] || { echo "prqueue: base branch $base_branch is not main; refusing to arm" >&2; return 1; }
  local ctxs
  ctxs=$(timeout 15 gh api "repos/$repo/branches/$base_branch/protection/required_status_checks" --jq '.contexts[]?, .checks[]?.context' 2>/dev/null) || { echo "prqueue: failed to read required_status_checks on $repo $base_branch" >&2; return 1; }
  printf "%s\n" "$ctxs" | grep -qx "ci-ok" \
    || { echo "prqueue: ci-ok not required on $repo $base_branch; not arming" >&2; return 1; }
  if ! printf "%s\n" "$ctxs" | grep -qx "pr-review" && [ "${verdict_ok:-0}" != "1" ]; then
    echo "prqueue: pr-review verdict not PASS yet (and pr-review not in required_status_checks) for $repo #$pr_num; deferring auto-merge to pr-review" >&2
    return 1
  fi
  timeout 15 gh pr merge "$pr_num" -R "$repo" --auto --squash >/dev/null || return 1
  return 0
}
