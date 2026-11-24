#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CHECK="$SCRIPT_DIR/../scripts/check.sh"
TEMPLATE="$SCRIPT_DIR/../references/template.md"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

pass_count=0
fail_count=0

assert_exit() {
  local expected="$1"
  local label="$2"
  shift 2
  set +e
  "$@" > /dev/null 2>&1
  local actual=$?
  set -e
  if [ "$actual" -eq "$expected" ]; then
    echo "  PASS: $label (exit $actual)"
    pass_count=$((pass_count + 1))
  else
    echo "  FAIL: $label (expected exit $expected, got $actual)" >&2
    fail_count=$((fail_count + 1))
  fi
}

# 1. Usage error when args missing
assert_exit 2 "usage error on missing args" bash "$CHECK"

# 2. Raw unfilled template MUST FAIL
assert_exit 1 "unfilled template fails --full" bash "$CHECK" "$TEMPLATE" --full
assert_exit 1 "unfilled template fails --lite" bash "$CHECK" "$TEMPLATE" --lite

# 3. Valid LITE spec MUST PASS --lite and FAIL --full (missing section 7)
cat << 'DOC' > "$TMP_DIR/valid_lite.md"
# UX Architecture — Dispatch Desk

- **Mode:** LITE
- **UX Vision (1 sentence):** Dispatchers triage and assign deliveries in under 30 seconds without leaving the main queue.

## 1. Outcomes, User Archetypes & Hypotheses
- **Primary Business Metric:** Cut average dispatch time from 3 min to 30 s.
- **H1:** We believe dispatch time drops 70% if dispatchers use an inline inspector drawer.

## 2. Application Posture & Conceptual Model
| Surface | Posture | Mental Model | Implementation Hidden |
|---|---|---|---|
| Dispatch Queue | Sovereign | Live Delivery Board | 6 normalized order/driver tables |
| Quick Assign | Transient | 1-click Driver Picker | Geohash routing API |

## 3. Semantic Grammar & Information Architecture
| Object (Noun) | Universal Actions | Specific Actions | Summary Attributes | Detail Attributes | Filter |
|---|---|---|---|---|---|
| Delivery | View, Search, Filter, Edit, Archive | Assign, Mark Delivered | Ref, Customer, Status, ETA | Items, Driver, History | Status, Zone |

## 4. Critical Task Flows & Excise Eradication
```mermaid
flowchart LR
  A["Queue"] --> B["Open Drawer"] --> C["Assign Driver"] --> D["Undo Toast + Closure"]
```

## 5. Inductive Screen Specs & UI Patterns
- **Inductive Main Instruction:** "Assign waiting deliveries to available drivers."
- Native `<button>` and `<dialog>` semantics preserved.

## 6. Psychological Bottlenecks, Error Proofing & Latency Budgets
- Direct click response `<= 100 ms`; optimistic assign `<= 400 ms`; background sync `> 10 s`.

## 8. UX Decisions, Open Questions & Validation Plan
- **UX-D1:** Use Two-Panel Split View instead of full-page detail hops.
- **Trunk Test Routes:** `/deliveries/402`, `/drivers/12`.
DOC

assert_exit 0 "valid LITE passes --lite" bash "$CHECK" "$TMP_DIR/valid_lite.md" --lite
assert_exit 1 "valid LITE fails --full (missing section 7)" bash "$CHECK" "$TMP_DIR/valid_lite.md" --full

# 4. Valid FULL spec MUST PASS --full
cat "$TMP_DIR/valid_lite.md" > "$TMP_DIR/valid_full.md"
cat << 'DOC' >> "$TMP_DIR/valid_full.md"

## 7. Analytics & UX Instrumentation
| Event | Trigger | Question |
|---|---|---|
| assign_completed | Driver assigned | Time-to-assign & completion rate |
DOC
assert_exit 0 "valid FULL passes --full" bash "$CHECK" "$TMP_DIR/valid_full.md" --full

# 5. Missing Mermaid diagram MUST FAIL
grep -v '```mermaid' "$TMP_DIR/valid_lite.md" > "$TMP_DIR/no_mermaid.md"
assert_exit 1 "missing mermaid fails" bash "$CHECK" "$TMP_DIR/no_mermaid.md" --lite

# 6. TODO placeholder MUST FAIL
cp "$TMP_DIR/valid_lite.md" "$TMP_DIR/has_todo.md"
echo "TODO finish empty state" >> "$TMP_DIR/has_todo.md"
assert_exit 1 "TODO placeholder fails" bash "$CHECK" "$TMP_DIR/has_todo.md" --lite

# 7. Missing UX-D1 MUST FAIL
sed 's/UX-D1/Decision 1/g' "$TMP_DIR/valid_lite.md" > "$TMP_DIR/no_uxd.md"
assert_exit 1 "missing UX-D1 fails" bash "$CHECK" "$TMP_DIR/no_uxd.md" --lite

echo "Summary: $pass_count passed, $fail_count failed"
[ "$fail_count" -eq 0 ]
