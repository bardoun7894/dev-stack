#!/bin/bash
# bash tests/test_deploy_guard.sh — hooks/deploy-guard.sh (G20): deploy only under an approved Deploy-it offer
H="$(cd "$(dirname "$0")/.." && pwd)/hooks/deploy-guard.sh"
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
mkdir -p "$T/bin"
cat >"$T/bin/tokyo-deploy" <<'SH'
#!/bin/bash
[ "$1" = status ] || exit 2
case "$2" in
  ok1) echo "proj approved on telegram" ;;
  no1) echo "proj declined on terminal" ;;
  pe1) echo "proj pending" ;;
  *) echo "tokyo-deploy: no such offer" >&2; exit 4 ;;
esac
SH
chmod +x "$T/bin/tokyo-deploy"
fails=0
# check <name> <allow|deny> <os> <command> [env...]
check() {
  local name=$1 want=$2 os=$3 c=$4 out got; shift 4
  out=$(jq -n --arg c "$c" '{tool_name:"Bash",tool_input:{command:$c},cwd:"/root/proj"}' | env PATH="$T/bin:$PATH" GATE_GUARD_UNAME="$os" DEPLOY_GUARD_CACHE="$T/cache" "$@" "$H" 2>/dev/null)
  if printf '%s' "$out" | grep -q '"deny"'; then got=deny; else got=allow; fi
  if [ "$got" = "$want" ] && { [ "$want" = allow ] || printf '%s' "$out" | grep -q 'G20: no approved Deploy-it offer'; }; then echo "ok   $name"; else echo "FAIL $name (got $got, want $want) $out"; fails=1; fi
}
check srv-unapproved deny Linux 'cd /root/proj && bash ops/dev-deploy.sh' A=1
check srv-gate-run-unapproved deny Linux 'gate-run deploy-proj 10m -- ./x' A=1
check srv-approved allow Linux 'TOKYO_OFFER=ok1 bash ops/dev-deploy.sh' A=1
check srv-approved-env allow Linux 'cd /root/proj && ./deploy.sh' TOKYO_OFFER=ok1
check srv-approved-gate-run allow Linux 'TOKYO_OFFER=ok1 gate-run deploy-proj 10m -- ./x' A=1
check srv-wrong-project deny Linux 'TOKYO_OFFER=ok1 gate-run deploy-other 10m -- ./x' A=1
check srv-declined deny Linux 'TOKYO_OFFER=no1 bash deploy.sh' A=1
check srv-pending deny Linux 'TOKYO_OFFER=pe1 bash deploy.sh' A=1
check srv-status-error deny Linux 'TOKYO_OFFER=zz9 bash deploy.sh' A=1
check srv-cat-readonly allow Linux 'cat ops/dev-deploy.sh' A=1
check srv-grep-readonly allow Linux 'grep -n curl ./deploy.sh' A=1
check srv-sed-readonly allow Linux 'sed -n 1,20p deploy-prod.sh' A=1
check srv-bash-n allow Linux 'bash -n ops/dev-deploy.sh' A=1
check srv-tokyo-deploy-yes allow Linux 'tokyo-deploy yes ab12cd' A=1
check srv-tokyo-deploy-ask allow Linux 'tokyo-deploy ask proj "ran deploy.sh tests"' A=1
check srv-skip allow Linux 'bash ops/dev-deploy.sh' A=1 DEPLOY_GUARD_SKIP=1
check srv-non-deploy allow Linux 'ls -la && pnpm test' A=1
check srv-commit-text allow Linux 'git commit -m "fix: bash ops/dev-deploy.sh docs"' A=1
check mac-ssh-deny deny Darwin 'ssh MyContabo "cd /root/x && bash ops/dev-deploy.sh"' A=1
check mac-ssh-host-deny deny Darwin "ssh other 'cd /x && ./deploy.sh'" A=1
check mac-ssh-approved allow Darwin 'TOKYO_OFFER=ok1 ssh MyContabo "cd /root/proj && bash ops/dev-deploy.sh"' A=1
check mac-ssh-cat allow Darwin 'ssh MyContabo "cat /root/x/ops/dev-deploy.sh"' A=1
check mac-ssh-gate-run deny Darwin 'ssh MyContabo "gate-run deploy-x 10m -- ./d"' A=1
check mac-local-no-ssh deny Darwin 'bash ops/dev-deploy.sh' A=1
# bypass regressions: each must deny without an approved offer
check bypass-bash-c deny Linux 'bash -c "./deploy.sh"' A=1
check bypass-sh-lc deny Linux "sh -lc 'bash ops/dev-deploy.sh'" A=1
check bypass-skip-in-command deny Linux 'bash deploy.sh # DEPLOY_GUARD_SKIP=1' A=1
check bypass-heredoc-bash deny Linux $'bash <<EOF\nbash deploy.sh\nEOF' A=1
check bypass-herestring deny Linux $'cat <<<"x"\nbash deploy.sh' A=1
check bypass-ssh-bash-s deny Darwin $'ssh MyContabo bash -s <<EOF\nbash deploy.sh\nEOF' A=1
check bypass-other-path deny Linux 'TOKYO_OFFER=ok1 bash /root/B/deploy.sh' A=1
check bypass-cd-prefix-substring deny Linux 'TOKYO_OFFER=ok1 cd /root/proj-old && bash deploy.sh' A=1
check bypass-case deny Linux 'bash ops/Deploy.sh' A=1
check bypass-quote-split deny Linux "bash ops/dev-dep''loy.sh" A=1
check bypass-timeout deny Linux 'timeout 600 bash deploy.sh' A=1
check bypass-xargs deny Linux 'xargs bash deploy.sh' A=1
check approved-other-project-path allow Linux 'TOKYO_OFFER=ok1 bash /root/proj/ops/dev-deploy.sh' A=1
# F1 regression: a deploy script path as an argument is not a deploy
check arg-cmp allow Linux 'cmp ~/.claude/hooks/deploy-guard.sh ~/code/x/hooks/dev-deploy.sh && echo same' A=1
check arg-cp allow Linux 'cp ops/dev-deploy.sh /tmp/dev-deploy.sh.bak' A=1
check arg-scp allow Linux 'scp ops/dev-deploy.sh MyContabo:/root/x/ops/' A=1
check arg-md5sum allow Linux 'md5sum ops/dev-deploy.sh' A=1
check arg-git-add allow Linux 'git add ops/dev-deploy.sh' A=1
check arg-heredoc allow Linux $'cat > notes.md <<EOF\nrun bash ops/dev-deploy.sh later\nEOF'
check arg-grep-deploy allow Linux 'grep -n deploy ops/dev-deploy.sh' A=1
check arg-mac-ssh-cmp-heredoc allow Darwin $'cmp a b && echo same; ssh MyContabo \'cmp ops/dev-deploy.sh x ; cp ops/dev-deploy.sh y ; python3 - <<PY\nprint("bash ops/dev-deploy.sh")\nPY\'' A=1
check exec-cd-bash deny Linux 'cd /root/x && bash ops/dev-deploy.sh' A=1
check exec-ssh-cd-dot-slash deny Darwin 'ssh MyContabo "cd x; ./scripts/deploy.sh"' A=1
check exec-env-sudo deny Linux 'FOO=1 sudo bash deploy.sh' A=1
check exec-source deny Linux 'source ops/deploy-prod.sh' A=1
# round 2: loops and heredoc bodies
check loop-test-scripts allow Linux 'for t in a b; do timeout 300 bash tests/$t.sh >/dev/null 2>&1; echo "$t rc=$?"; done' A=1
check heredoc-then-bash-script allow Linux $'cat > /tmp/p.sh <<\'EOF\'\nt \'for d in a b; do ssh MyContabo "bash /root/$d/ops/dev-deploy.sh"; done\' x\nEOF\nbash /tmp/p.sh' A=1
check var-script-path allow Linux 'S=/tmp/x; bash $S/probe.sh deploy' A=1
check ssh-bash-s-stdin allow Darwin 'ssh MyContabo bash -s < /tmp/deploy-notes.sh' A=1
check loop-deploy-ssh deny Darwin 'for d in a b; do ssh MyContabo "bash /root/$d/ops/dev-deploy.sh"; done' A=1
check loop-deploy-plain deny Linux 'for d in a b; do bash /root/$d/ops/dev-deploy.sh; done' A=1
check glob-deploy deny Linux 'bash ops/dep*.sh' A=1
exit $fails
