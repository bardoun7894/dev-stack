#!/bin/bash
# bash tests/test_comms_guard.sh — hooks/comms-guard.sh (G24): Stop hook warns on banned phrases, em-dash >1, emoji
H="$(cd "$(dirname "$0")/.." && pwd)/hooks/comms-guard.sh"
T=$(mktemp -d); fails=0

run_hook() { # json_stdin
  printf '%s' "$1" | "$H" 2>/dev/null
}

check_hit() { # name jsonl_content expected_substr
  local f="$T/$1.jsonl" out rc
  printf '%s\n' "$2" > "$f"
  out=$(run_hook "{\"transcript_path\":\"$f\"}"); rc=$?
  if [ "$rc" = 0 ] && printf '%s' "$out" | grep -q '"systemMessage"' && printf '%s' "$out" | grep -qi "$3"; then
    echo "ok   $1"
  else
    echo "FAIL $1 (rc=$rc, want hit '$3') out=$out"
    fails=1
  fi
}

check_clean() { # name jsonl_content
  local f="$T/$1.jsonl" out rc
  printf '%s\n' "$2" > "$f"
  out=$(run_hook "{\"transcript_path\":\"$f\"}"); rc=$?
  if [ "$rc" = 0 ] && [ -z "$out" ]; then
    echo "ok   $1"
  else
    echo "FAIL $1 (rc=$rc, want empty) out=$out"
    fails=1
  fi
}

# 1. Banned phrase hits
check_hit hit-great-question \
  '{"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":"Great question, fixed the bug."}]}}' \
  "great question"

check_hit hit-honest-truth \
  '{"role":"assistant","content":"Here'\''s the honest truth about this module."}' \
  "here's the honest truth"

check_hit hit-canonical-prose \
  '{"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":"This is the canonical approach for hooks."}]}}' \
  "canonical"

# 2. Clean message
check_clean clean-msg \
  '{"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":"Fixed. All 4 tests pass."}]}}'

# 3. Canonical followed by URL or path-like token -> allowed
check_clean canonical-url \
  '{"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":"Set the canonical https://example.com/blog/post and canonical /root/code/dev-stack/hooks/foo.sh or canonical URL https://a.b."}]}}'

# 4. Code block and inline backtick skip
check_clean skip-fenced-and-inline \
  '{"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":"Updated fixtures:\n```markdown\nGreat question! Here'\''s the honest truth 🚀 — a — b\n```\nAnd inline `great question` or `load-bearing` is ignored."}]}}'

# 5. Skip tool_use and thinking blocks
check_clean skip-thinking-and-tool-use \
  '{"type":"assistant","message":{"role":"assistant","content":[{"type":"thinking","thinking":"Great question, let me be clear — one — two 🚀"},{"type":"tool_use","name":"Bash","input":{"command":"echo great question"}},{"type":"text","text":"Done."}]}}'

# 6. Only last assistant message is checked
check_clean only-last-assistant \
  '{"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":"Great question earlier."}]}}
{"type":"user","message":{"role":"user","content":"next"}}
{"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":"Fixed in commit abc1234."}]}}'

# 7. Em dash: 1 is allowed, >1 is flagged
check_clean one-em-dash \
  '{"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":"One dash — allowed."}]}}'

check_hit two-em-dashes \
  '{"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":"First — second — third."}]}}' \
  "em-dash"

# 8. Emoji flagged outside code, checkmarks allowed
check_hit hit-emoji \
  '{"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":"All tests pass 🚀"}]}}' \
  "emoji"

check_clean checkmark-not-emoji \
  '{"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":"Status: ✓ pass ✔ ok ✗ fail ✘ skip"}]}}'

# 9. Malformed input / missing file -> silent exit 0
out=$(printf 'not json at all' | "$H" 2>/dev/null); rc=$?
[ "$rc" = 0 ] && [ -z "$out" ] && echo "ok   malformed-json" || { echo "FAIL malformed-json (rc=$rc, out=$out)"; fails=1; }

out=$(printf '{"transcript_path":"/nonexistent/path/xyz.jsonl"}' | "$H" 2>/dev/null); rc=$?
[ "$rc" = 0 ] && [ -z "$out" ] && echo "ok   missing-transcript" || { echo "FAIL missing-transcript (rc=$rc, out=$out)"; fails=1; }

rm -rf "$T"; exit $fails
