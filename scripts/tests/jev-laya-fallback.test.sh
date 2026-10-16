#!/usr/bin/env bash
# Tests for the jev → local Laya fallback, with a fake upstream that answers 402 and a fake Laya
# daemon (stdlib only, no torch), so they never depend on the live TypeSafe outage or the weights.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
JEV="$HERE/../../bin/jev"
T="$(mktemp -d)"
fail=0

cat > "$T/fake.py" <<'PY'
import json, sys
from http.server import BaseHTTPRequestHandler, HTTPServer
mode, portfile, calls = sys.argv[1], sys.argv[2], sys.argv[3]
class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        open(calls, "a").write("call\n")
        if mode == "402":
            self.send_response(402); self.end_headers()
            self.wfile.write(b'{"detail":{"error_type":"billing_error"}}'); return
        answers = {}
        for k, q in body["questions"].items():
            t = q["type"]
            if t == "choice":
                answers[k] = {"type": t, "choice": sorted(q["criteria"])[1], "confidence": 0.05}
            elif t == "noul":
                answers[k] = {"type": t, "noul": 0.3, "confidence": 0.7}
            else:
                answers[k] = {"type": t, "score": 1.2, "confidence": 0.06}
        out = json.dumps({"model": "laya/typed-decisions", "answers": answers}).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
        self.wfile.write(out)
s = HTTPServer(("127.0.0.1", 0), H)
open(portfile, "w").write(str(s.server_address[1]))
s.serve_forever()
PY

python3 "$T/fake.py" 402 "$T/up.port" "$T/up.calls" & UP=$!
python3 "$T/fake.py" laya "$T/laya.port" "$T/laya.calls" & LAYA=$!
trap 'kill $UP $LAYA 2>/dev/null; rm -rf "$T"' EXIT
for _ in $(seq 50); do [ -s "$T/up.port" ] && [ -s "$T/laya.port" ] && break; sleep 0.1; done
UPP=$(cat "$T/up.port"); LP=$(cat "$T/laya.port")

check() { # name want got
  if [ "$2" = "$3" ]; then echo "PASS $1"; else echo "FAIL $1: want '$2' got '$3'"; fail=1; fi
}
# Upstream always 402; the OpenRouter-style URL makes route() skip the real TypeSafe key.
run() {
  out=$(env JEV_DECISIONS_URL="http://127.0.0.1:$UPP" OPENROUTER_API_KEY=x JEV_LOG_DIR="$T/log" \
    JEV_LAYA_URL="${LAYA_URL-http://127.0.0.1:$LP/decisions}" "$@" 2>"$T/err" </dev/null); rc=$?
}

run python3 "$JEV" route "say OK" -q
check laya-up-answer T1 "$out"
check laya-up-rc 0 "$rc"
grep -q "fallback=laya" "$T/err" && echo "PASS stderr-marks-fallback" || { echo "FAIL stderr-marks-fallback: $(cat "$T/err")"; fail=1; }

run python3 "$JEV" choice "pick" a="first" b="second" -s "x"
check json-engine laya "$(printf '%s' "$out" | python3 -c 'import json,sys;print(json.load(sys.stdin).get("engine"))')"

run python3 "$JEV" noul "is it" -s "x"
check noul-json-engine laya "$(printf '%s' "$out" | python3 -c 'import json,sys;print(json.load(sys.stdin).get("engine"))')"

run python3 "$JEV" route "say OK" -q --min 0.4
check min-fails-closed 2 "$rc"

echo '{"state":"x","questions":{"q":{"type":"noul","instructions":"is it"}}}' > "$T/raw.json"
out=$(env JEV_DECISIONS_URL="http://127.0.0.1:$UPP" OPENROUTER_API_KEY=x JEV_LOG_DIR="$T/log" \
  JEV_LAYA_URL="http://127.0.0.1:$LP/decisions" python3 "$JEV" raw < "$T/raw.json" 2>/dev/null)
check raw-engine laya "$(printf '%s' "$out" | python3 -c 'import json,sys;print(json.load(sys.stdin).get("engine"))')"

: > "$T/laya.calls"
run env JEV_NO_LAYA=1 python3 "$JEV" route "say OK" -q
check opt-out-rc 3 "$rc"
check opt-out-no-laya-call 0 "$(wc -l < "$T/laya.calls" | tr -d ' ')"

LAYA_URL="http://127.0.0.1:1/decisions" run python3 "$JEV" route "say OK" -q
check laya-down-rc 3 "$rc"
grep -q "HTTP 402" "$T/err" && echo "PASS laya-down-keeps-jev-error" || { echo "FAIL laya-down-keeps-jev-error: $(cat "$T/err")"; fail=1; }

run python3 "$JEV" route "say OK" -q --log lt
check log-engine laya "$(python3 -c 'import json,sys;print(json.loads(open(sys.argv[1]).readlines()[-1]).get("engine"))' "$T/log/decisions.jsonl")"
run python3 "$JEV" tune lt
check tune-skips-laya 0 "$(printf '%s' "$out" | python3 -c 'import json,sys;print(json.load(sys.stdin)["decisions"])')"

for f in "$HERE/../../skills/jev/scripts/jev-browse.mjs" "$HERE/../../skills/jev/scripts/jev-page.mjs"; do
  grep -q "JEV_NO_LAYA" "$f" && echo "PASS e2e-judge-opts-out $(basename "$f")" \
    || { echo "FAIL e2e-judge-opts-out $(basename "$f")"; fail=1; }
done

exit $fail
