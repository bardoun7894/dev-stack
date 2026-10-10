#!/bin/bash
# bash tests/test_world_skill_track.sh: hooks/world-skill-track.sh emits `track add --kind skill` and always exits 0 silently
HOOK="$(cd "$(dirname "$0")/.." && pwd)/hooks/world-skill-track.sh"
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
mkdir "$T/bin"
printf '#!/bin/bash\nprintf "%%s\\t" "$@" >> %s/log; echo >> %s/log\n' "$T" "$T" > "$T/bin/track"
chmod +x "$T/bin/track"
fail=0
bad() { echo "FAIL $1"; fail=1; }
wait_log() { for _ in $(seq 1 30); do [ -s "$T/log" ] && return; sleep 0.1; done; }

out=$(printf '%s' '{"tool_name":"Skill","tool_input":{"skill":"view-md"},"cwd":"/Users/x/code/MyProj","session_id":"s1"}' | PATH="$T/bin:$PATH" bash "$HOOK"); rc=$?
wait_log
[ $rc = 0 ] || bad "exit $rc"
[ -z "$out" ] || bad "printed: $out"
line=$(cat "$T/log" 2>/dev/null)
case "$line" in *"--kind"*"skill"*) ;; *) bad "no kind skill: $line";; esac
case "$line" in *"--project"*"MyProj"*) ;; *) bad "project: $line";; esac
case "$line" in *"--ref"*"view-md"*) ;; *) bad "ref: $line";; esac
case "$line" in *"skill:view-md:s1:"*) ;; *) bad "key: $line";; esac
case "$line" in *"--source"*"live"*) ;; *) bad "source: $line";; esac

rm -f "$T/log"
out=$(printf 'not json {{' | PATH="$T/bin:$PATH" bash "$HOOK"); rc=$?
sleep 0.3
[ $rc = 0 ] || bad "garbage exit $rc"
[ -z "$out" ] || bad "garbage printed: $out"
[ ! -s "$T/log" ] || bad "garbage emitted a call"

out=$(printf '%s' '{"tool_input":{"skill":"x"},"cwd":"/a/b","session_id":"s"}' | WORLD_TRACK=0 PATH="$T/bin:$PATH" bash "$HOOK"); rc=$?
sleep 0.3
[ $rc = 0 ] && [ ! -s "$T/log" ] || bad "WORLD_TRACK=0"

out=$(printf '%s' '{"tool_input":{"skill":"x"},"cwd":"/a/b","session_id":"s"}' | PATH="/usr/bin:/bin" bash "$HOOK"); rc=$?
[ $rc = 0 ] && [ -z "$out" ] || bad "missing track"

[ $fail = 0 ] && echo "RESULT: all ok"
exit $fail
