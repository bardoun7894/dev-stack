#!/bin/bash
# comms-guard.sh — Stop hook (G24, warn only). Checks the last assistant message in transcript_path against
# hooks/comms-banned.txt, >1 em dash (U+2014), and emoji. Prints {"systemMessage":"comms-guard: <hits>"} on hit.
# Never blocks; exits 0 always.
set -u
in=""
[ -t 0 ] || in=$(cat 2>/dev/null || true)
[ -n "$in" ] || exit 0

DIR="$(cd "$(dirname "$0")" && pwd)"
BANNED="${COMMS_BANNED_FILE:-$DIR/comms-banned.txt}"
[ -f "$BANNED" ] || BANNED="$HOME/code/dev-stack/hooks/comms-banned.txt"
[ -f "$BANNED" ] || exit 0

printf '%s' "$in" | python3 -c '
import json, os, re, sys

banned_path = sys.argv[1]
try:
    payload = json.load(sys.stdin)
except Exception:
    sys.exit(0)

tp = payload.get("transcript_path") if isinstance(payload, dict) else None
if not isinstance(tp, str) or not tp or not os.path.isfile(tp):
    sys.exit(0)

try:
    with open(tp, "rb") as f:
        f.seek(0, os.SEEK_END)
        sz = f.tell()
        f.seek(max(0, sz - 524288))
        raw_lines = f.read().decode("utf-8", "replace").splitlines()
except Exception:
    sys.exit(0)

def extract_assistant_text(obj):
    if not isinstance(obj, dict):
        return None
    msg = obj.get("message") if isinstance(obj.get("message"), dict) else obj
    role = msg.get("role") or obj.get("role") or obj.get("type")
    if role != "assistant":
        return None
    content = msg.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for b in content:
            if isinstance(b, str):
                parts.append(b)
            elif isinstance(b, dict):
                btype = b.get("type", "")
                if btype in ("tool_use", "thinking", "redacted_thinking", "tool_result"):
                    continue
                if btype == "text" and isinstance(b.get("text"), str):
                    parts.append(b["text"])
        if parts:
            return "\n".join(parts)
    return None

last_text = None
for line in reversed(raw_lines):
    line = line.strip()
    if not line:
        continue
    try:
        obj = json.loads(line)
    except Exception:
        continue
    t = extract_assistant_text(obj)
    if t is not None:
        last_text = t
        break

if not last_text:
    sys.exit(0)

# Strip fenced code blocks and inline backticks
cleaned = re.sub(r"```[\s\S]*?```|~~~[\s\S]*?~~~", " ", last_text)
cleaned = re.sub(r"`[^`\n]*`", " ", cleaned)
norm = cleaned.replace("\u2019", "\x27")

try:
    with open(banned_path, "r", encoding="utf-8") as bf:
        phrases = [ln.strip() for ln in bf if ln.strip() and not ln.lstrip().startswith("#")]
except Exception:
    sys.exit(0)

hits = []
URL_OR_PATH_AFTER = re.compile(
    r"^\s*[:=()-]?\s*(?:https?://|[/~.]\S|[A-Za-z0-9_.-]+/[A-Za-z0-9_./-]+|(?:url|uri|path|link|href|route)s?\b)",
    re.IGNORECASE,
)

for p in phrases:
    pl = p.lower()
    if pl == "canonical":
        for m in re.finditer(r"\bcanonical\b", norm, re.IGNORECASE):
            tail = norm[m.end():]
            if not URL_OR_PATH_AFTER.search(tail):
                hits.append("canonical")
                break
    else:
        pat = r"\b" + r"\s+".join(re.escape(w) for w in pl.split()) + r"\b"
        if re.search(pat, norm, re.IGNORECASE):
            hits.append(p)

em_count = cleaned.count("\u2014")
if em_count > 1:
    hits.append("em-dash x%d" % em_count)

EMOJI_RE = re.compile(r"[\U0001F300-\U0001FAFF\U0001F1E6-\U0001F1FF\u2600-\u2712\u2715\u2716\u2719-\u27BF]")
if EMOJI_RE.search(cleaned):
    hits.append("emoji")

if hits:
    print(json.dumps({"systemMessage": "comms-guard: " + ", ".join(hits)}))
' "$BANNED" 2>/dev/null || true
exit 0
