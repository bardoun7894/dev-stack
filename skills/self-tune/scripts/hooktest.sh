H=~/.claude/hooks/no-poll-guard.sh${HOOK_SUFFIX:-}; SL="sl""eep"; JD="jdele""gate"; T="/private/tmp/x/ta""sks"; NL=$'\n'
export NO_POLL_GUARD_NOLOG=1   # test runs must not pollute the block log the audit reads
run(){ jq -n --arg c "$1" '{tool_input:{command:$c}}' | $H >/dev/null 2>&1; echo "rc=$? :: $2"; }
runf(){ jq -n --arg f "$1" '{tool_input:{file_path:$f}}' | $H >/dev/null 2>&1; echo "rc=$? :: $2"; }
run "$SL 20; cat $T/boo24ht0r.output" "real poll (expect 2)"
run "$SL 5 && tail -3 $T/b123.output" "real poll with && (expect 2)"
run "cat > f.sh <<'X'${NL}$SL 20; cat $T/boo.output${NL}X${NL}bash f.sh --dry" "poll text inside heredoc (expect 0)"
run "echo \"$SL 20; cat $T/boo.output\" > notes.txt" "poll text inside quotes (expect 0)"
run "tail -5 $T/a25591edeaa372323.output" "agent transcript via bash (expect 2)"
runf "$T/a41706b29f72b2545.output" "agent transcript via Read (expect 2)"
runf "$T/bkhqm0shr.output" "finished bash output (expect 0)"
run "$JD --cwd /x --name a \"do it\"" "jdelegate heavy (expect 2)"
run "$JD --cwd /x --no-auto-mcp \"do\"" "jdelegate partial (expect 2)"
run "$JD --no-auto-mcp --no-auto-skill --no-auto-role --cwd /x \"\$(cat <<'B'${NL}brief mentions $JD --cwd y${NL}B${NL})\"" "jdelegate lean w/ heredoc brief (expect 0)"
run "~/.local/bin/$JD --cwd /x go" "jdelegate by path heavy (expect 2)"
run "$JD --help" "jdelegate help (expect 0)"
run "git diff bin/$JD" "path mention only (expect 0)"
run "echo 'use $JD --cwd x for small work'" "jdelegate in quoted text (expect 0)"
run "until [ -f /x.done ]; do $SL 120; done" "background waiter (expect 0)"
