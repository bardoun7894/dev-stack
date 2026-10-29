#!/usr/bin/env bash
# D4: the headless claude run file written by server-agent.sh start gives the worker a session id and a NAME.resume script
# that resumes the same session with a prompt file. Dry run + fake claude; nothing touches /root/agents.
# SERVER_AGENT overrides the script under test (skills/where-to-work is not tracked in this repo).
set -uo pipefail
SA=${SERVER_AGENT:-$HOME/code/dev-stack/skills/where-to-work/scripts/server-agent.sh}
[ -f "$SA" ] || { echo "SKIP: $SA not found"; exit 0; }
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
D=$T/agents; mkdir -p "$D" "$T/bin" "$T/proj"
fail=0; ok() { echo "ok   $*"; }; bad() { echo "FAIL $*"; fail=1; }
echo "do the thing" > "$T/brief.txt"
cat > "$T/bin/claude" <<'FAKE'
#!/usr/bin/env bash
echo "claude $*" >> "$FAKE_LOG"; echo "stdin: $(cat)" >> "$FAKE_LOG"; echo "answer-from-fake"
FAKE
chmod +x "$T/bin/claude"
export FAKE_LOG=$T/claude.log PATH="$T/bin:$PATH" SERVER_AGENT_DIR=$D HEADLESS=1 SERVER_AGENT_DRY=1
bash "$SA" start gw "$T/proj" "$T/brief.txt" claude 2>&1 | sed -n '/^==== run file ====$/,/^==== pane line ====$/p' | sed '1d;$d' > "$T/run.sh"
[ -s "$T/run.sh" ] && ok "dry run printed a run file" || { bad "no run file"; exit 1; }
echo "the brief" > "$D/gw.brief"
bash "$T/run.sh" > "$T/out1" 2>&1; rc=$?
[ "$rc" = 0 ] && ok "first run exits 0" || bad "first run rc=$rc"
sid=$(cat "$D/gw.session" 2>/dev/null)
[[ $sid =~ ^[0-9a-f-]{36}$ ]] && ok "session id written: $sid" || bad "no session id in $D/gw.session"
grep -q -- "--session-id $sid" "$FAKE_LOG" && ok "first run launches claude with --session-id" || bad "no --session-id in $(cat "$FAKE_LOG")"
grep -q "stdin: the brief" "$FAKE_LOG" && ok "first run reads the brief" || bad "brief not on stdin"
[ -x "$D/gw.resume" ] || [ -f "$D/gw.resume" ] && ok "gw.resume written" || bad "gw.resume missing"
grep -q "answer-from-fake" "$D/gw.log" && ok "first answer is in the log" || bad "log lacks the first answer"
# the resume: same run file, prompt file on stdin, session resumed, log appended not truncated
sed -i.bak "s#exec bash $D/gw.run#exec bash $T/run.sh#" "$D/gw.resume"
printf 'gate tk finished rc=0; output tail:\nfine\n; continue from your handover\n' > "$D/gw.resume.prompt"
bash "$D/gw.resume" "$D/gw.resume.prompt" > "$T/out2" 2>&1; rc=$?
[ "$rc" = 0 ] && ok "resume exits 0" || bad "resume rc=$rc"
grep -q -- "--resume $sid" "$FAKE_LOG" && ok "resume uses --resume with the same session id" || bad "no --resume $sid"
grep -q "stdin: gate tk finished rc=0" "$FAKE_LOG" && ok "resume feeds the prompt file" || bad "prompt not on stdin"
[ "$(grep -c answer-from-fake "$D/gw.log")" = 2 ] && ok "log kept and appended" || bad "log was truncated: $(cat "$D/gw.log")"
# non-headless claude and other harnesses get no session / resume machinery
HEADLESS=0 bash "$SA" start gi "$T/proj" "$T/brief.txt" claude 2>&1 | grep -q "gi.resume" && bad "interactive run file mentions .resume" || ok "interactive claude run file has no .resume"
exit $fail
