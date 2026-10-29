#!/usr/bin/env bash
# Offline tests for bin/gmail-draft and bin/tokyo-inbox (no network, ssh is a shim)
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
BIN="$HERE/../../bin"
fail=0
ok()  { echo "ok   $1"; }
bad() { echo "FAIL $1"; fail=1; }
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT

# gmail-draft (a): no send call anywhere
if grep -nE '\.send\(|send_message|\.send\b' "$BIN/gmail-draft" >/dev/null; then bad "gmail-draft contains a send call"; else ok "no .send( in gmail-draft"; fi

# (b) help lists exactly login/list/read/draft
h="$(HOME="$T/h" uv run --script "$BIN/gmail-draft" --help 2>&1)"
cmds="$(printf '%s\n' "$h" | sed -n 's/^[[:space:]]*{\(.*\)}[[:space:]]*$/\1/p' | head -1)"
[ "$cmds" = "login,list,read,draft" ] && ok "help lists login,list,read,draft" || bad "help commands: '$cmds'"

# (c) missing secret -> exit 2 with setup text
mkdir -p "$T/h"
out="$(HOME="$T/h" uv run --script "$BIN/gmail-draft" list 2>&1)"; rc=$?
[ $rc -eq 2 ] && ok "missing secret exit 2" || bad "exit $rc"
case "$out" in *"Desktop app"*"client_secret.json"*"gmail-draft login"*) ok "setup text";; *) bad "setup text: $out";; esac

# tokyo-inbox with ssh shim
mkdir -p "$T/bin"
cat > "$T/bin/ssh" <<'S'
#!/usr/bin/env bash
cat >/dev/null
cat "$FAKE_SSH_OUT"
S
chmod +x "$T/bin/ssh"
now="$(date -u +%Y-%m-%dT%H:%M:%S.000Z)"
old="$(date -u -v-20d +%Y-%m-%dT%H:%M:%S.000Z 2>/dev/null || date -u -d '-20 days' +%Y-%m-%dT%H:%M:%S.000Z)"
later="$(date -u -v+1M +%Y-%m-%dT%H:%M:%S 2>/dev/null || date -u -d '+1 minute' +%Y-%m-%dT%H:%M:%S)"
earlier="$(date -u -v-1H +%Y-%m-%dT%H:%M:%S 2>/dev/null || date -u -d '-1 hour' +%Y-%m-%dT%H:%M:%S)"
soon="$(date -v+3d +%F 2>/dev/null || date -d '+3 days' +%F)"
far="$(date -v+30d +%F 2>/dev/null || date -d '+30 days' +%F)"
{
echo "===BIZ==="
for i in 1 2 3; do echo "{\"ts\":\"$now\",\"jid\":\"a@lid\",\"phone\":\"212600000111@s.whatsapp.net\",\"pushName\":\"Alice\",\"text\":\"msg$i\",\"action\":\"forwarded\"}"; done
echo "{\"ts\":\"$now\",\"jid\":\"b@lid\",\"phone\":\"212600000222@s.whatsapp.net\",\"pushName\":\"Bob\",\"text\":\"hi\",\"action\":\"muted\"}"
echo "{\"ts\":\"$old\",\"jid\":\"c@lid\",\"phone\":\"212600000333@s.whatsapp.net\",\"pushName\":\"Old\",\"text\":\"x\",\"action\":\"forwarded\"}"
echo "{\"ts\":\"$now\",\"jid\":\"e@lid\",\"phone\":\"212600000444@s.whatsapp.net\",\"pushName\":\"Eve\",\"text\":\"hello\",\"action\":\"forwarded\"}"
echo "{\"ts\":\"$now\",\"jid\":\"f@lid\",\"phone\":\"212600000555@s.whatsapp.net\",\"pushName\":\"Frank\",\"text\":\"yo\",\"action\":\"forwarded\"}"
echo "===SITE==="
echo "{\"ts\":\"$now\",\"jid\":\"d@lid\",\"pushName\":\"Dina\",\"text\":\"\",\"action\":\"saved\",\"groupName\":\"site\"}"
echo "===OUT==="
echo "+212600000444|$later"
echo "212600000555|$earlier"
echo "===PROMISES==="
echo "[{\"id\":1,\"content\":\"send quote\",\"made_to\":\"Alice\",\"due_date\":\"$soon\",\"status\":\"pending\"},{\"id\":2,\"content\":\"later\",\"made_to\":null,\"due_date\":\"$far\",\"status\":\"pending\"}]"
} > "$T/fx1"
o="$(PATH="$T/bin:$PATH" FAKE_SSH_OUT="$T/fx1" "$BIN/tokyo-inbox" --days 7)"; rc=$?
[ $rc -eq 0 ] && ok "tokyo-inbox exit 0" || bad "tokyo-inbox rc $rc"
[ "$(printf '%s\n' "$o" | grep -c 'Alice')" -ge 2 ] && ok "Alice appears (inbound + promise)" || bad "Alice count"
[ "$(printf '%s\n' "$o" | grep -c '^.*Alice.*(3)')" -eq 1 ] && ok "Alice grouped x3" || bad "grouping: $o"
printf '%s' "$o" | grep -q Bob && bad "muted Bob listed" || ok "muted skipped"
printf '%s' "$o" | grep -q Old && bad "old listed" || ok "old skipped"
printf '%s' "$o" | grep -q Dina && ok "site lead listed" || bad "site lead missing"
printf '%s' "$o" | grep -q 'send quote' && ok "promise due listed" || bad "promise missing"
printf '%s' "$o" | grep -q 'later' && bad "far promise listed" || ok "far promise skipped"
printf '%s' "$o" | grep -q Eve && bad "replied Eve listed" || ok "replied sender dropped"
printf '%s' "$o" | grep -q Frank && ok "unreplied Frank kept (older outbound)" || bad "Frank missing"
printf '%s\n' "$o" | head -1 | grep -q 'unanswered' && ok "header shows unanswered" || bad "header: $o"
j="$(PATH="$T/bin:$PATH" FAKE_SSH_OUT="$T/fx1" "$BIN/tokyo-inbox" --json)"
printf '%s' "$j" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert "waiting" in d and "promises" in d; assert [e["replied"] for e in d["answered"]]==[True] and not any(e["replied"] for e in d["waiting"])' && ok "json shape + replied flag" || bad "json shape"

# 30-line cap
{
echo "===BIZ==="
for i in $(seq 1 60); do echo "{\"ts\":\"$now\",\"jid\":\"s$i@lid\",\"phone\":\"2126000$i@s.whatsapp.net\",\"pushName\":\"P$i\",\"text\":\"t\",\"action\":\"forwarded\"}"; done
echo "===SITE==="
echo "===PROMISES==="
echo "[]"
} > "$T/fx2"
n="$(PATH="$T/bin:$PATH" FAKE_SSH_OUT="$T/fx2" "$BIN/tokyo-inbox" | wc -l | tr -d ' ')"
[ "$n" -le 30 ] && ok "cap: $n lines" || bad "cap: $n lines"
exit $fail
