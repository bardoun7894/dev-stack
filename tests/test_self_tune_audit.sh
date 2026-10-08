#!/bin/bash
# bash tests/test_self_tune_audit.sh — audit.sh keeps findings from its ps loops: a finding must make the run not "clean"
SRC=${AUDIT:-$(cd "$(dirname "$0")/.." && pwd)/skills/self-tune/scripts/audit.sh}
T=$(mktemp -d)
trap 'rm -rf "$T"' EXIT
mkdir -p "$T/bin" "$T/home"
# the real psql check would read this machine's Postgres; a copy points it at a stub that reports 0 databases
sed "s#/opt/homebrew/opt/postgresql@16/bin/psql#$T/bin/psql#" "$SRC" > "$T/audit.sh"
printf '#!/bin/bash\necho 0\n' > "$T/bin/psql"
chmod +x "$T/bin/psql"
AUDIT="$T/audit.sh"
# fake ps: the claude -p worker line for the first query, a bare jdelegate line for the second; no real process is read
cat > "$T/bin/ps" <<'EOF'
#!/bin/bash
case "$*" in
  *etime*) echo "  4242 01:02 claude -p --model claude-haiku-5-5 --dangerously-skip-permissions brief" ;;
  *) echo "  5555 node /opt/jdelegate /x/brief.md" ;;
esac
EOF
printf '#!/bin/bash\nexit 1\n' > "$T/bin/pgrep"
chmod +x "$T/bin/ps" "$T/bin/pgrep"
out=$(HOME="$T/home" PATH="$T/bin:$PATH" bash "$AUDIT" 2>&1)
fail=0
echo "$out" | grep -q 'OLD: claude -p worker pid 4242' || { echo "FAIL: OLD finding missing"; fail=1; }
echo "$out" | grep -q 'HEAVY: jdelegate without lean flags, pid 5555' || { echo "FAIL: HEAVY finding missing"; fail=1; }
echo "$out" | grep -q 'audit: clean' && { echo "FAIL: printed 'audit: clean' after findings"; fail=1; }
[ $fail = 0 ] && echo "audit test: ok" || { echo "$out"; exit 1; }
