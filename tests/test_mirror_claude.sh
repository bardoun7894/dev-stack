#!/bin/bash
# bash tests/test_mirror_claude.sh — scripts/mirror-claude-to-servers.sh: both servers are targets, only the rule paths go
S="$(cd "$(dirname "$0")/.." && pwd)/scripts/mirror-claude-to-servers.sh"
fails=0
check() { # name cond-exit-code
  if [ "$2" = 0 ]; then echo "ok   $1"; else echo "FAIL $1"; fails=1; fi
}

out=$("$S" --dry-run 2>&1); rc=$?
check "dry-run exits 0" $rc
printf '%s' "$out" | grep -q 'MyContabo';    check "MyContabo is a target" $?
printf '%s' "$out" | grep -q 'MediaContabo'; check "MediaContabo is a target" $?
for p in CLAUDE.md comms.md reference agents-parked skills skills-parked; do
  printf '%s' "$out" | grep -q "$p"; check "mirrors $p" $?
done
printf '%s' "$out" | grep -q 'settings.json'; [ $? -ne 0 ]; check "never mirrors settings.json" $?
out=$("$S" --dry-run MediaContabo 2>&1)
printf '%s' "$out" | grep -q 'MyContabo'; [ $? -ne 0 ]; check "explicit host limits targets" $?

# Symlink guard: tar -h sends link targets, so only links inside the allowed roots may be sent.
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
mkdir -p "$T/home/skills" "$T/home/reference" "$T/home/agents-parked" "$T/home/skills-parked" "$T/stack/skills/one" "$T/secret" "$T/bin"
echo rule > "$T/home/CLAUDE.md"; echo c > "$T/home/comms.md"; echo body > "$T/stack/skills/one/SKILL.md"; echo key > "$T/secret/id"
ln -s "$T/stack/skills/one" "$T/home/skills/one"
cat > "$T/bin/ssh" <<'EOF'
#!/bin/bash
cat > "$FAKE_TAR_OUT"
EOF
chmod +x "$T/bin/ssh"
run() { CLAUDE_HOME="$T/home" MIRROR_LINK_ROOTS="$T/home $T/stack" FAKE_TAR_OUT="$T/sent.tar" PATH="$T/bin:$PATH" "$S" fakehost 2>&1; }
out=$(run); rc=$?
check "links inside the roots are sent" $rc
tar -xOf "$T/sent.tar" skills/one/SKILL.md 2>/dev/null | grep -q body; check "a linked skill arrives as its content" $?
ln -s "$T/secret" "$T/home/skills/leak"; rm -f "$T/sent.tar"
out=$(run); rc=$?; [ $rc -ne 0 ]; check "a link outside the roots stops the run" $?
printf '%s' "$out" | grep -q 'points outside the allowed roots'; check "the refusal names the link" $?
[ ! -e "$T/sent.tar" ]; check "nothing is sent after a refusal" $?
rm "$T/home/skills/leak"; ln -s "$T/missing" "$T/home/skills/broken"
out=$(run); rc=$?; [ $rc -ne 0 ]; check "a broken link stops the run" $?
[ $fails = 0 ] && echo "ALL OK" || exit 1
