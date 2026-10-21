#!/usr/bin/env bash
# harness-health.sh: read-only weekly check of agent harnesses, skills and the MyContabo link.
# Prints OK / WARN lines only. Changes nothing.
set -u
H="$HOME"; DS="$H/code/dev-stack"
ok(){ echo "OK   $*"; }; warn(){ echo "WARN $*"; }

# 1. Rules sync drift
out=$(python3 "$DS/scripts/sync-rules-harnesses.py" 2>&1 | grep -E '^would')
[ -z "$out" ] && ok "rules: all harnesses match CLAUDE.md" || warn "rules out of sync: $(echo "$out" | awk '{print $2}' | tr '\n' ' ')"

# 2. Duplicate skills that are copies (not links) with different content
drift=""; for n in $(find "$H/.claude/skills" "$H/.agents/skills" "$H/.codex/skills" "$H/.gemini/skills" "$H/.gemini/config/skills" "$H/.gemini/antigravity-ide/skills" "$H/.config/opencode/skills" "$H/.opencode/skills" -mindepth 1 -maxdepth 1 2>/dev/null | xargs -n1 basename | sort | uniq -d); do
  hs=$(for d in "$H/.claude/skills" "$H/.agents/skills" "$H/.codex/skills" "$H/.gemini/skills" "$H/.gemini/config/skills" "$H/.gemini/antigravity-ide/skills" "$H/.config/opencode/skills" "$H/.opencode/skills"; do [ -f "$d/$n/SKILL.md" ] && md5 -q "$d/$n/SKILL.md"; done | sort -u | wc -l | tr -d ' ')
  [ "$hs" -gt 1 ] && drift="$drift $n($hs versions)"; done
[ -z "$drift" ] && ok "skills: no diverged duplicates" || warn "skills diverged:$drift"

# 3. Delegate skills whose CLI is missing
dead=""; for f in "$H"/.agents/skills/*-delegate; do c=$(basename "$f" -delegate); case $c in cursor) c=cursor-agent;; esac; command -v "$c" >/dev/null 2>&1 || dead="$dead $c"; done
[ -z "$dead" ] && ok "delegates: all CLIs installed" || warn "delegate CLIs missing:$dead"

# 4. Model router
l=$(grep -E 'probed' "$H/.config/jev-router/health.log" 2>/dev/null | tail -1)
echo "$l" | grep -q 'dead 0' && ok "router: $l" || warn "router: ${l:-no health log}"

# 5. Claude CLI update
r=$(cat "$H/.claude/.last-update-result.json" 2>/dev/null | python3 -c 'import json,sys;d=json.load(sys.stdin);print(d["outcome"],d["version_to"],d["timestamp"][:10])' 2>/dev/null)
echo "$r" | grep -q '^success' && ok "claude update: $r" || warn "claude update: ${r:-unknown}"

# 6. Factory worker: Temporal reachable, worker process alive, errors only if log written in last 24h
nc -z -w5 100.64.0.1 7233 2>/dev/null && ok "temporal server reachable" || warn "temporal server 100.64.0.1:7233 unreachable"
L="$H/Library/Logs/factory-temporal-worker.out.log"
pid=$(launchctl list | awk '/factory-temporal-worker$/{print $1}'); if [ "$pid" != "-" ] && lsof -nP -a -p "$pid" -iTCP:7233 -sTCP:ESTABLISHED >/dev/null 2>&1; then ok "factory worker connected to Temporal"; else warn "factory worker not connected to Temporal (see $L)"; fi

# 6b. Long-running Claude sessions (token cost)
old=$(ps ax -o etime=,command= | grep -E "versions/[0-9.]+ .*--model opus" | grep -v grep | awk '$1 ~ /-/' | wc -l | tr -d ' ')
cur=$(ls -t "$H/.local/share/claude/versions" | head -1)
stale=$(ps ax -o command= | grep -E "claude/versions/" | grep -v grep | grep -vc "versions/$cur ")
[ "$old" -eq 0 ] && ok "no Opus sessions older than a day" || warn "$old Opus Claude sessions running longer than a day ($stale on an old Claude version)"

# 7. MyContabo
if ssh -o BatchMode=yes -o ConnectTimeout=10 MyContabo true 2>/dev/null; then
  ok "ssh MyContabo reachable"
  mac=$(md5 -q "$H/.claude/CLAUDE.md"); srv=$(ssh -o BatchMode=yes MyContabo 'md5sum /root/.claude/CLAUDE.md' | cut -d' ' -f1)
  [ "$mac" = "$srv" ] && ok "server CLAUDE.md matches Mac" || warn "server CLAUDE.md differs from Mac"
  ssh -o BatchMode=yes MyContabo 'bash -s' <<'R'
d=$(df / --output=pcent | tail -1 | tr -d " %"); [ "$d" -lt 90 ] && echo "OK   server disk ${d}%" || echo "WARN server disk ${d}% full"
p=$(docker ps --format "{{.Names}} {{.Ports}}" | grep -E "0\.0\.0\.0:(5432|6379|3306|9200|27017)->" | awk '{print $1}' | tr "\n" " ")
[ -z "$p" ] && echo "OK   no public database ports" || echo "WARN public database ports: $p"
u=$(docker ps --filter health=unhealthy --format "{{.Names}}" | tr "\n" " "); [ -z "$u" ] && echo "OK   no unhealthy containers" || echo "WARN unhealthy containers: $u"
f=$(systemctl --failed --no-legend --plain 2>/dev/null | awk '{print $1}' | grep -v networkd-wait-online | tr "\n" " "); [ -z "$f" ] && echo "OK   no failed services" || echo "WARN failed services: $f"
for c in jdelegate gemini; do command -v $c >/dev/null || echo "WARN server missing $c"; done
R
else warn "ssh MyContabo unreachable"; fi
for p in com.mycontabo.ssh-reverse-tunnel com.tokyo.cliproxy-tunnel com.tokyo.wa-tunnel com.mohamedbardouni.factory-temporal-worker; do
  launchctl list | grep -q "^[0-9].*$p$" && ok "running $p" || warn "not running $p"; done
