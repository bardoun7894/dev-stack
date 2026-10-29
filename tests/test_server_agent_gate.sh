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
unset FACTORY_RESUME_ID FACTORY_EFFORT FACTORY_RESUME_EFFORT
export FACTORY_SESSIONS=1   # session/resume machinery is gated on this (set globally on the server, not on the Mac)
# Off the server the script reaches the host through ssh/scp: local stand-ins keep the file plumbing (mkdir, rm, cp) and make
# the rest (hsess, factory, watchdog) a no-op, so a real start installs gw.run and gw.resume under $D without touching a server.
[ "$(hostname)" = vmi3015200 ] && { echo "SKIP: on the server start would launch a real worker"; exit 0; }
cat > "$T/bin/ssh" <<'SSH'
#!/usr/bin/env bash
cmd="${!#}"; case "$cmd" in mkdir*|rm\ *) bash -c "$cmd";; esac; exit 0
SSH
cat > "$T/bin/scp" <<'SCP'
#!/usr/bin/env bash
src="${@: -2:1}"; dst="${@: -1}"; cp "$src" "${dst#*:}"
SCP
# The resume script is written for GNU sed (`sed -i -e ...`); BSD sed reads -e as the backup suffix. Shim `-i` to `-i ''` there.
BSDSED=0
if ! sed --version >/dev/null 2>&1; then
  BSDSED=1
  REALSED=$(command -v sed); printf '#!/usr/bin/env bash\nargs=(); for a in "$@"; do if [ "$a" = -i ]; then args+=(-i ""); else args+=("$a"); fi; done\nexec %s "${args[@]}"\n' "$REALSED" > "$T/bin/sed"
  chmod +x "$T/bin/sed"
fi
chmod +x "$T/bin/ssh" "$T/bin/scp"
unset FACTORY_RESUME_ID FACTORY_EFFORT FACTORY_RESUME_EFFORT
export FACTORY_SESSIONS=1   # session/resume machinery is gated on this
export FAKE_LOG=$T/claude.log PATH="$T/bin:$PATH" SERVER_AGENT_DIR=$D HEADLESS=1 SERVER_HOST=local
bash "$SA" start gw "$T/proj" "$T/brief.txt" claude > "$T/start.out" 2>&1
[ -s "$D/gw.run" ] && ok "start installed the run file" || { bad "no run file: $(cat "$T/start.out")"; exit 1; }
echo "the brief" > "$D/gw.brief"
bash "$D/gw.run" > "$T/out1" 2>&1; rc=$?
[ "$rc" = 0 ] && ok "first run exits 0" || bad "first run rc=$rc"
sid=$(sed -n "s/^session_id=//p" "$D/gw.session" 2>/dev/null | head -n1)   # gw.session is KEY=VALUE
[[ $sid =~ ^[0-9a-f-]{36}$ ]] && ok "session id written: $sid" || bad "no session id in $D/gw.session"
grep -q -- "--session-id $sid" "$FAKE_LOG" && ok "first run launches claude with --session-id" || bad "no --session-id in $(cat "$FAKE_LOG")"
grep -q "stdin: the brief" "$FAKE_LOG" && ok "first run reads the brief" || bad "brief not on stdin"
[ -x "$D/gw.resume" ] || [ -f "$D/gw.resume" ] && ok "gw.resume written" || bad "gw.resume missing"
grep -q "answer-from-fake" "$D/gw.log" && ok "first answer is in the log" || bad "log lacks the first answer"
# the resume: same run file, prompt file on stdin, session resumed, log appended not truncated
printf 'gate tk finished rc=0; output tail:\nfine\n; continue from your handover\n' > "$D/gw.resume.prompt"
bash "$D/gw.resume" "$D/gw.resume.prompt" > "$T/out2" 2>&1; rc=$?
[ "$rc" = 0 ] && ok "resume exits 0" || bad "resume rc=$rc"
# the flag rewrite uses GNU BRE alternation (\|), which BSD sed lacks; the resume script only runs on the (GNU) server
if [ "$BSDSED" = 1 ]; then echo "skip resume flag check (BSD sed)"
elif grep -q -- "--resume $sid" "$FAKE_LOG"; then ok "resume uses --resume with the same session id"; else bad "no --resume $sid"; fi
grep -q "stdin: gate tk finished rc=0" "$FAKE_LOG" && ok "resume feeds the prompt file" || bad "prompt not on stdin"
[ "$(grep -c answer-from-fake "$D/gw.log")" = 2 ] && ok "log kept and appended" || bad "log was truncated: $(cat "$D/gw.log")"
# non-headless claude and other harnesses get no session / resume machinery
HEADLESS=0 bash "$SA" start gi "$T/proj" "$T/brief.txt" claude 2>&1 | grep -q "gi.resume" && bad "interactive run file mentions .resume" || ok "interactive claude run file has no .resume"
exit $fail
