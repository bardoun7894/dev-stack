#!/usr/bin/env bash
# Tests for scripts/server/server-health.sh.
#
# Puts stub binaries on PATH (curl, systemctl, pm2, docker, crontab, df) and
# points the script at temp fixture dirs for nginx conf, backups, logs and
# state, plus an isolated ENV_FILE for Telegram credentials and a stub
# python3 that records messages instead of calling api.telegram.org.
#
# Run: bash scripts/server/test_server_health.sh

set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
SCRIPT="$HERE/server-health.sh"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
export PATH="$T/bin:$PATH"

# Fixture layout used by every test.
mkdir -p "$T/bin" "$T/nginx" "$T/backups" "$T/logs" "$T/state" "$T/state/pm2" "$T/state/docker" "$T/state/health" "$T/cron-targets"

pass=0; fail=0
ok() { echo "PASS $1"; pass=$((pass+1)); }
bad() { echo "FAIL $1: $2"; fail=$((fail+1)); }

PY_LOG="$T/state/health/py.log"
touch "$PY_LOG"

# --- ENV_FILE stub ---
ENV_FILE="$T/state/health/tokyo.env"
mkdir -p "$(dirname "$ENV_FILE")"
printf 'TELEGRAM_BOT_TOKEN=tg-FAKE-token-for-test-0123\nTELEGRAM_USER_ID=1234567\n' > "$ENV_FILE"

# Stub installer: writes stub binaries for curl/systemctl/pm2/docker/crontab/df
# according to features in $HEALTH_STUB.
stub_install() {
  rm -rf "$T/bin/curl" "$T/bin/systemctl" "$T/bin/pm2" "$T/bin/docker" "$T/bin/crontab" "$T/bin/df" "$T/bin/chkrootkit" 2>/dev/null

  # curl: per-host map of "name=code"
  local host_codes="${HEALTH_STUB_HOSTS:-}"
  cat > "$T/bin/curl" <<CURL
#!/usr/bin/env bash
# stub curl: parses -w '%{http_code}' and an https URL arg, picks from HEALTH_STUB_HOSTS.
code="\${HEALTH_STUB_CODE:-200}"
for u in "\$@"; do
  case "\$u" in
    https://*)
      host="\${u#https://}"; host="\${host%%/*}"
      map=\$(printf '%s\n' "\$HEALTH_STUB_HOSTS" | awk -F'=' -v h="\$host" '\$1==h {print \$2; exit}')
      if [ -n "\$map" ]; then code="\$map"; fi
      ;;
  esac
done
printf '%s' "\$code"
exit 0
CURL
  chmod +x "$T/bin/curl"

  cat > "$T/bin/getent" <<'GETENT'
#!/usr/bin/env bash
# stub getent ahosts NAME: no output (no DNS) for names listed in HEALTH_STUB_NODNS
for n in ${HEALTH_STUB_NODNS:-}; do [ "$n" = "${2:-}" ] && exit 2; done
echo "192.0.2.1 STREAM ${2:-}"
GETENT
  chmod +x "$T/bin/getent"

  cat > "$T/bin/systemctl" <<'SYSD'
#!/usr/bin/env bash
echo "${HEALTH_STUB_FAILED:-}"
SYSD
  chmod +x "$T/bin/systemctl"

  cat > "$T/bin/pm2" <<'PM2'
#!/usr/bin/env bash
if [ "${1:-}" = "jlist" ]; then
  printf 'pm2 noise: not json\n%s\n' "${HEALTH_STUB_PM2LIST:-[]}"
  exit 0
fi
exit 0
PM2
  chmod +x "$T/bin/pm2"

  cat > "$T/bin/docker" <<'DOCKER'
#!/usr/bin/env bash
# ps --format => HEALTH_STUB_DOCKER; ps -a => HEALTH_STUB_DOCKER_ALL;
# inspect => line "name=output" from HEALTH_STUB_INSPECT; port => line "name" in HEALTH_STUB_PORTS
case "${1:-}" in
  ps) if [ "${2:-}" = "-a" ]; then printf '%s\n' "${HEALTH_STUB_DOCKER_ALL:-}"; else printf '%s\n' "${HEALTH_STUB_DOCKER:-}"; fi ;;
  inspect) n="${!#}"; printf '%s\n' "${HEALTH_STUB_INSPECT:-}" | awk -F'=' -v n="$n" '$1==n {sub(/^[^=]*=/,""); print; exit}' ;;
  port) n="${2:-}"; printf '%s\n' "${HEALTH_STUB_PORTS:-}" | grep -Fx "$n" >/dev/null && echo "80/tcp -> 0.0.0.0:8080" ;;
esac
exit 0
DOCKER
  chmod +x "$T/bin/docker"

  cat > "$T/bin/crontab" <<'CRON'
#!/usr/bin/env bash
if [ "${1:-}" = "-l" ]; then
  printf '%s\n' "${HEALTH_STUB_CRONTAB:-}"
fi
CRON
  chmod +x "$T/bin/crontab"

  cat > "$T/bin/df" <<'DF'
#!/usr/bin/env bash
# df -P (tab-separated). Allow override via env, default a healthy mount.
printf '%s\n' "${HEALTH_STUB_DF:-Filesystem     1024-blocks    Used Available Capacity Mounted on
/dev/sda1            10000     3000      7000      30% /}"
DF
  chmod +x "$T/bin/df"
}

export HEALTH_STUB_HOSTS= HEALTH_STUB_FAILED= HEALTH_STUB_PM2LIST= HEALTH_STUB_DOCKER= HEALTH_STUB_CRONTAB= HEALTH_STUB_DF= HEALTH_STUB_NODNS= HEALTH_STUB_DOCKER_ALL= HEALTH_STUB_INSPECT= HEALTH_STUB_PORTS=
# Set mtime N days ago (portable)
age_touch() { python3 -c "import os,sys,time; t=time.time()-float(sys.argv[2])*86400; os.utime(sys.argv[1],(t,t))" "$1" "$2"; }

# Helper: run the script with all stubs in place, capture stdout and rc.
run_script() {
  stub_install
  out=$(ENV_FILE="$ENV_FILE" STATE_DIR="$T/state/health" BACKUP_DIRS="$T/backups" \
    NGINX_CONF_DIR="$T/nginx/sites-enabled" VAR_LOG_CHKROOTKIT="$T/logs/chkrootkit.log" \
    CRON_LOG_DIR="$T/cron-targets" \
    HEALTH_PY_LOG="$PY_LOG" \
    bash "$SCRIPT" --dry-run "$@" 2>&1)
  rc=$?
  echo "$out"
}

# Common environment that points the script at every stub/fixture.
export ENV_FILE STATE_DIR="$T/state/health" BACKUP_DIRS="$T/backups"
export NGINX_CONF_DIR="$T/nginx/sites-enabled" VAR_LOG_CHKROOTKIT="$T/logs/chkrootkit.log"
export CRON_LOG_DIR="$T/cron-targets"
export HEALTH_PY_LOG="$PY_LOG"
mkdir -p "$T/nginx/sites-enabled"
mkdir -p "$T/backups" "$T/cron-targets" "$T/logs"

# Write nginx site confs
cat > "$T/nginx/sites-enabled/beldify.conf" <<'NG'
server_name beldify.example.com;
listen 443 ssl;
NG
cat > "$T/nginx/sites-enabled/ostudio.conf" <<'NG'
server_name ostudio.example.com;
listen 443 ssl;
NG
cat > "$T/nginx/sites-enabled/local.conf" <<'NG'
server_name localhost;
NG
cat > "$T/nginx/sites-enabled/iponly.conf" <<'NG'
server_name 10.0.0.5;
NG

# ---- 1. 502 site alerts ----
HEALTH_STUB_HOSTS="beldify.example.com=502
ostudio.example.com=200"
out="$(run_script)"
echo "$out" | grep -q "site: beldify.example.com 502" && ok "502-beldify" || bad "502-beldify" "missing 502 finding in: $out"
echo "$out" | grep -q "ostudio.example.com 502" && bad "502-clean" "ostudio flagged despite 200: $out" || ok "502-clean"

# ---- 1b. unresolvable names are skipped; resolvable 000 is reported ----
printf 'server_name nodns.example.com;\n' > "$T/nginx/sites-enabled/nodns.conf"
printf 'server_name down.example.com;\n' > "$T/nginx/sites-enabled/down.conf"
HEALTH_STUB_NODNS="nodns.example.com"
HEALTH_STUB_HOSTS="nodns.example.com=000
down.example.com=000"
out="$(run_script)"
echo "$out" | grep -q "nodns.example.com" && bad "nodns-skipped" "no-DNS name reported: $out" || ok "nodns-skipped"
echo "$out" | grep -q "site: down.example.com 000" && ok "resolving-000" || bad "resolving-000" "resolving 000 not reported: $out"
HEALTH_STUB_NODNS=""
rm -f "$T/nginx/sites-enabled/nodns.conf" "$T/nginx/sites-enabled/down.conf"

# ---- 2. 20-byte backup alerts; normal one does not ----
head -c 1048576 /dev/zero > "$T/backups/beldify-2026-10-07.sql.gz"; age_touch "$T/backups/beldify-2026-10-07.sql.gz" 1
printf '%020d' 0 > "$T/backups/beldify-2026-10-08.sql.gz"
head -c 2000 /dev/zero > "$T/backups/ostudio-2026-10-07.sql.gz"; age_touch "$T/backups/ostudio-2026-10-07.sql.gz" 1
head -c 1500 /dev/zero > "$T/backups/ostudio-2026-10-08.sql.gz"
# cartx: only a 3-day-old file, so it is missing
head -c 5000 /dev/zero > "$T/backups/cartx-2026-10-05.sql.gz"; age_touch "$T/backups/cartx-2026-10-05.sql.gz" 3

HEALTH_STUB_HOSTS="beldify.example.com=200
ostudio.example.com=200"
out="$(run_script)"
echo "$out" | grep -q "backup: beldify .*20 bytes" && ok "backup-20b" || bad "backup-20b" "no 20-byte finding in: $out"
echo "$out" | grep -q "backup: cartx .*missing" && ok "backup-missing" || bad "backup-missing" "no missing finding in: $out"
echo "$out" | grep -q "backup: ostudio" && bad "backup-normal" "ostudio (>=1024 bytes) flagged: $out" || ok "backup-normal"

# ---- 3. failed unit ----
HEALTH_STUB_FAILED="nginx.service failed
"
HEALTH_STUB_HOSTS="beldify.example.com=200
ostudio.example.com=200"
out="$(run_script)"
echo "$out" | grep -q "unit: nginx.service failed" && ok "unit" || bad "unit" "missing nginx.service failed finding: $out"

# ---- 4. pm2 restart jump 0 -> 30 alerts; second run without growth does not ----
PM2_BASE='[{"name":"web","pid":1,"pm2_env":{"status":"online","restart_time":0},"monit":{"cpu":0}},{"name":"db","pid":1,"pm2_env":{"status":"online","restart_time":1},"monit":{"cpu":0}}]'
# --dry-run never writes the baseline, so seed the previous restart counts ("count<TAB>name") directly.
printf '0\tweb\n1\tdb\n' > "$T/state/health/pm2-restarts.previous"
PM2_BAD='[{"name":"web","pid":1,"pm2_env":{"status":"online","restart_time":30},"monit":{"cpu":0}},{"name":"db","pid":1,"pm2_env":{"status":"online","restart_time":1},"monit":{"cpu":0}}]'
HEALTH_STUB_PM2LIST="$PM2_BAD"
HEALTH_STUB_FAILED=""
HEALTH_STUB_HOSTS="beldify.example.com=200
ostudio.example.com=200"
out="$(run_script)"
echo "$out" | grep -q "pm2: web restarted more than 20 times" && ok "pm2-jump" || bad "pm2-jump" "no jump finding in: $out"
echo "$out" | grep -q "pm2: db restarted" && bad "pm2-stable" "stable app flagged: $out" || ok "pm2-stable"

# Second run with the same restart counts (no growth) must be silent.
PM2_SAME="$PM2_BAD"
printf '30\tweb\n1\tdb\n' > "$T/state/health/pm2-restarts.previous"
HEALTH_STUB_PM2LIST="$PM2_SAME"
out="$(run_script)"
echo "$out" | grep -q "^\[server-health\] pm2:" && bad "pm2-dedupe" "still emitting pm2 findings after stable run: $out" || ok "pm2-dedupe"

# ---- 5. cron log with 30 "No such container" lines alerts ----
LOGF="$T/cron-targets/app.log"
: > "$LOGF"
for i in $(seq 1 50); do
  printf 'line %s: No such container: nope\n' "$i" >> "$LOGF"
done
# Make sure the file mtime is fresh (<= 2h)
touch "$LOGF"
HEALTH_STUB_CRONTAB="0 * * * * /usr/local/bin/t.sh >> $T/cron-targets/app.log 2>&1"
HEALTH_STUB_HOSTS="beldify.example.com=200
ostudio.example.com=200"
HEALTH_STUB_FAILED=""
out="$(run_script)"
echo "$out" | grep -q "cronlog: .*cron-targets/app.log .*last line:.*No such container" && ok "cronlog" || bad "cronlog" "no cron alert in: $out"

# ---- 6. cron log with only 5 error lines does NOT alert (under 20 / last 50) ----
LOGF2="$T/cron-targets/quiet.log"
: > "$LOGF2"
for i in $(seq 1 50); do
  [ $((i % 10)) -eq 0 ] && printf 'line %s: Error happened\n' "$i" >> "$LOGF2" || printf 'line %s: ok\n' "$i" >> "$LOGF2"
done
touch "$LOGF2"
HEALTH_STUB_CRONTAB="0 * * * * /usr/local/bin/q.sh >> $T/cron-targets/quiet.log 2>&1"
out="$(run_script)"
echo "$out" | grep -q "cronlog: .*cron-targets/quiet.log" && bad "cronlog-quiet" "quiet cron log flagged: $out" || ok "cronlog-quiet"

# ---- 7. dedupe: same finding twice sends only one message ----
LOGF="$T/cron-targets/app.log"
touch "$LOGF"
HEALTH_STUB_CRONTAB="0 * * * * /usr/local/bin/t.sh >> $T/cron-targets/app.log 2>&1"
HEALTH_STUB_HOSTS="beldify.example.com=200
ostudio.example.com=200"
out="$(run_script)"
echo "$out" | grep -q "cronlog: .*cron-targets/app.log" && ok "dedupe-1" || bad "dedupe-1" "no alert on first run: $out"

# --dry-run never records sent findings, so record the first run's finding as sent just now.
key=$(echo "$out" | grep "^\[server-health\] cronlog: .*cron-targets/app.log" | head -1 | sed 's/^\[server-health\] //')
printf '%s\t%s\n' "$(date +%s)" "$key" >> "$T/state/health/findings.sent"
# Second run, the same finding MUST NOT be reprinted.
out="$(run_script)"
echo "$out" | grep -q "cronlog: .*cron-targets/app.log" && bad "dedupe-2" "duplicated finding on second run: $out" || ok "dedupe-2"

# ---- 8. recovery: when the finding clears, send "recovered: ..." ----
LOGF="$T/cron-targets/app.log"
: > "$LOGF"
for i in $(seq 1 50); do printf 'ok line %s\n' "$i" >> "$LOGF"; done
touch "$LOGF"
out="$(run_script)"
echo "$out" | grep -q "recovered: .*cronlog: .*cron-targets/app.log" && ok "recovery" || bad "recovery" "no recovered: line: $out"

# ---- 9. chkrootkit: ignore /tmp, /usr/lib/python3/.../fail2ban/tests/, and the
#       runc-process lstat line; alert once per unique /usr/bin path ----
LOGD="$T/logs/chkrootkit.log"
mkdir -p "$(dirname "$LOGD")"
cp /dev/null "$LOGD"
cat >> "$LOGD" <<CHK
Searching for suspicious files and dirs, it may take a while...
WARNING: The following suspicious files and directories were found:
/tmp/evil-bin
/usr/lib/python3/dist-packages/fail2ban/tests/data.bin
/usr/lib/python3/dist-packages/twisted/x.py
Possible Linux.Xor.DDoS installed:
lstat(/tmp/runc-process123) failed
Checking \`ifpromisc'... 
eth0: not promisc
PACKET SNIFFER(/lib/systemd/systemd-networkd[1])
/usr/bin/notwarned
CHK
touch "$LOGD"
HEALTH_STUB_HOSTS="beldify.example.com=200
ostudio.example.com=200"
out="$(run_script --rebaseline)"
echo "$out" | grep -q "chkrootkit:" && bad "chkrootkit-seed" "first run not silent: $out" || ok "chkrootkit-seed"
printf 'WARNING: more\n/usr/bin/x\n/usr/bin/x\n' >> "$LOGD"
HEALTH_STUB_HOSTS="beldify.example.com=200
ostudio.example.com=200"
HEALTH_STUB_FAILED=""
out="$(run_script)"
echo "$out" | grep -q "chkrootkit: /usr/bin/x$" && ok "chkrootkit" || bad "chkrootkit" "no /usr/bin/x alert in: $out"
[ "$(echo "$out" | grep -c "chkrootkit: /usr/bin/x$")" = "1" ] && ok "chkrootkit-dedupe" || bad "chkrootkit-dedupe" "found multiple /usr/bin/x alerts: $out"
echo "$out" | grep -q "chkrootkit: /tmp/" && bad "chkrootkit-tmp" "/tmp/ flagged: $out" || ok "chkrootkit-tmp"
echo "$out" | grep -q "fail2ban/tests" && bad "chkrootkit-fail2ban" "fail2ban path flagged: $out" || ok "chkrootkit-fail2ban"
echo "$out" | grep -q "runc-process" && bad "chkrootkit-runc" "runc flagged: $out" || ok "chkrootkit-runc"

out="$(run_script --rebaseline)"
out="$(run_script)"
echo "$out" | grep -q "chkrootkit: /usr/bin/x" && bad "chkrootkit-rebaseline" "rebaseline did not absorb: $out" || ok "chkrootkit-rebaseline"

# ---- 9a. chkrootkit: baseline written in en_US order (mixed case/underscore),
#       current list in another order; no comm sort warnings, only new paths ----
CL="$T/state/locale"; mkdir -p "$CL"
# en_US collation: punctuation ignored, case-insensitive first -> alpha, _beta, Zed
printf '/usr/lib/alpha\n/usr/lib/_beta\n/usr/lib/Zed\n' > "$CL/chkrootkit.baseline"
printf 'WARNING: suspicious\n/usr/lib/_beta\n/usr/lib/alpha\n/usr/lib/Zed\n/usr/lib/Newone\n/usr/lib/_new2\n' > "$LOGD"
stub_install
lout="$(ENV_FILE="$ENV_FILE" STATE_DIR="$CL" BACKUP_DIRS="$T/backups" \
  NGINX_CONF_DIR="$T/nginx/sites-enabled" VAR_LOG_CHKROOTKIT="$LOGD" \
  CRON_LOG_DIR="$T/cron-targets" HEALTH_PY_LOG="$PY_LOG" \
  bash "$SCRIPT" --dry-run 2>"$CL/stderr")"
grep -q "not in sorted order" "$CL/stderr" && bad "chkrootkit-locale-warn" "comm warned: $(cat "$CL/stderr")" || ok "chkrootkit-locale-warn"
[ "$(echo "$lout" | grep -c '^chkrootkit:\|chkrootkit: /usr/lib/')" = "2" ] \
  && echo "$lout" | grep -q "chkrootkit: /usr/lib/Newone$" && echo "$lout" | grep -q "chkrootkit: /usr/lib/_new2$" \
  && ! echo "$lout" | grep -qE "chkrootkit: /usr/lib/(alpha|_beta|Zed)$" \
  && ok "chkrootkit-locale-new-only" || bad "chkrootkit-locale-new-only" "unexpected: $lout"

# ---- 9b. docker: down restart-policy container, unbound ports, clean ----
HEALTH_STUB_DOCKER_ALL="obs-n8n
web-ok
web-nobind
manual-job"
HEALTH_STUB_INSPECT="obs-n8n=always exited 1 Error: cannot assign 100.64.0.1:5678
web-ok=always running 1
web-nobind=unless-stopped running 1
manual-job=no exited 0"
HEALTH_STUB_PORTS="web-ok"
out="$(run_script)"
echo "$out" | grep -q "docker: obs-n8n exited .*cannot assign" && ok "docker-down" || bad "docker-down" "no down finding: $out"
echo "$out" | grep -q "docker: web-nobind .*not bound" && ok "docker-noports" || bad "docker-noports" "no port finding: $out"
echo "$out" | grep -Eq "docker: (web-ok|manual-job)" && bad "docker-clean" "clean container flagged: $out" || ok "docker-clean"
HEALTH_STUB_DOCKER_ALL=""; HEALTH_STUB_INSPECT=""; HEALTH_STUB_PORTS=""

# ---- 9c. real send: curl hit with bot URL; findings.sent written only on success ----
cat > "$T/bin/curl" <<'CURLSEND'
#!/usr/bin/env bash
for u in "$@"; do
  case "$u" in
    https://api.telegram.org/bot*/sendMessage) echo "$u" >> "$CURL_LOG"; cat >/dev/null; exit "${CURL_RC:-0}" ;;
    https://sendtest.example.com/*) printf '502'; exit 0 ;;
    https://*) printf '200'; exit 0 ;;
  esac
done
printf '200'
CURLSEND
chmod +x "$T/bin/curl"
export CURL_LOG="$T/curl.log"
sendrun() { ENV_FILE="$ENV_FILE" STATE_DIR="$T/state/send" BACKUP_DIRS="$T/none" NGINX_CONF_DIR="$T/nginx/sites-enabled" \
  VAR_LOG_CHKROOTKIT="$T/none" bash "$SCRIPT" 2>&1; }
rm -rf "$T/state/send" "$CURL_LOG"; : > "$CURL_LOG"
printf 'server_name sendtest.example.com;\n' > "$T/nginx/sites-enabled/sendtest.conf"
HEALTH_STUB_HOSTS="sendtest.example.com=502"
CURL_RC=22 sendrun >/dev/null
grep -q "bottg-FAKE-token-for-test-0123/sendMessage" "$CURL_LOG" && ok "send-url" || bad "send-url" "curl not called with bot URL: $(cat "$CURL_LOG")"
[ -s "$T/state/send/findings.sent" ] && bad "send-fail-unrecorded" "finding recorded after failed send" || ok "send-fail-unrecorded"
CURL_RC=0 sendrun >/dev/null
grep -q "sendtest.example.com 502" "$T/state/send/findings.sent" 2>/dev/null && ok "send-ok-recorded" || bad "send-ok-recorded" "finding not recorded after successful send"
: > "$CURL_LOG"; CURL_RC=0 sendrun >/dev/null
[ -s "$CURL_LOG" ] && bad "send-deduped" "resent within 6h" || ok "send-deduped"
rm -f "$T/nginx/sites-enabled/sendtest.conf"
stub_install

# ---- 10. --dry-run never invokes curl to api.telegram.org ----
# Re-do a clean site alert + check curl never touches api.telegram.
HEALTH_STUB_HOSTS="beldify.example.com=502
ostudio.example.com=200"
HEALTH_STUB_FAILED=""
HEALTH_STUB_CRONTAB=""
out="$(ENV_FILE="$ENV_FILE" STATE_DIR="$T/state/dry" BACKUP_DIRS="$T/backups" \
  NGINX_CONF_DIR="$T/nginx/sites-enabled" VAR_LOG_CHKROOTKIT="$T/logs/chkrootkit.log" \
  CRON_LOG_DIR="$T/cron-targets" \
  HEALTH_PY_LOG="$PY_LOG" \
  DOCKER_IGNORE='^(ostudio-dev-|board-test-)' \
  bash "$SCRIPT" --dry-run 2>&1)"
echo "$out" | grep -q "site: beldify.example.com 502" && ok "dryrun-banner" || bad "dryrun-banner" "no finding printed: $out"
# Ensure our curl stub never received a url for api.telegram.org
echo "$out" | grep -q "api.telegram.org" && bad "dryrun-no-api" "dry-run still mentioned api.telegram.org: $out" || ok "dryrun-no-api"

# Direct check: hook curl to fail loudly if it sees api.telegram.org during --dry-run.
cat > "$T/bin/curl" <<'CURLFAIL'
#!/usr/bin/env bash
for u in "$@"; do
  case "$u" in
    *api.telegram.org*) echo "TELEGRAM CALL IN DRY-RUN: $u" >&2; exit 9;;
  esac
done
# benign default
printf '%s' "${HEALTH_STUB_CODE:-200}"
exit 0
CURLFAIL
chmod +x "$T/bin/curl"
out="$(ENV_FILE="$ENV_FILE" STATE_DIR="$T/state/dry" BACKUP_DIRS="$T/backups" \
  NGINX_CONF_DIR="$T/nginx/sites-enabled" VAR_LOG_CHKROOTKIT="$T/logs/chkrootkit.log" \
  CRON_LOG_DIR="$T/cron-targets" \
  HEALTH_PY_LOG="$PY_LOG" \
  DOCKER_IGNORE='^(ostudio-dev-|board-test-)' \
  bash "$SCRIPT" --dry-run 2>&1)"
echo "$out" | grep -q "TELEGRAM CALL IN DRY-RUN" && bad "dryrun-guard" "curl stub was hit with api.telegram.org: $out" || ok "dryrun-guard"

# ---- 11. world hooks: a live (non-dry) alert emits `track add --kind alert`, recovery emits --kind recovery ----
printf '#!/usr/bin/env bash\nprintf "%%s\\t" "$@" >> "%s/track.log"; echo >> "%s/track.log"\n' "$T" "$T" > "$T/bin/track"
chmod +x "$T/bin/track"
tw() { for _ in $(seq 1 30); do grep -q "$1" "$T/track.log" 2>/dev/null && return 0; sleep 0.1; done; return 1; }
live_run() {
  PATH="$T/bin:$PATH" ENV_FILE="$ENV_FILE" STATE_DIR="$T/state/world" BACKUP_DIRS="$T/backups" \
    NGINX_CONF_DIR="$T/nginx/sites-enabled" VAR_LOG_CHKROOTKIT="$T/logs/chkrootkit.log" \
    HEALTH_PY_LOG="$PY_LOG" bash "$SCRIPT" >/dev/null 2>&1
}
LOGF="$T/cron-targets/app.log"
: > "$LOGF"; for i in $(seq 1 50); do printf 'line %s: No such container: nope\n' "$i" >> "$LOGF"; done; touch "$LOGF"
HEALTH_STUB_CRONTAB="0 * * * * /usr/local/bin/t.sh >> $T/cron-targets/app.log 2>&1"
stub_install
rm -f "$T/track.log"
live_run
tw "alert" && ok "world-alert" || bad "world-alert" "no alert call: $(cat "$T/track.log" 2>/dev/null)"
a="$(grep -a "alert" "$T/track.log" | head -1)"
case "$a" in *"down"*"--project"*"server"*|*"--project"*"server"*"down"*) ok "world-alert-flags";; *) bad "world-alert-flags" "$a";; esac
case "$a" in *"mycontabo"*) ok "world-alert-host";; *) bad "world-alert-host" "$a";; esac
rm -f "$T/track.log"
: > "$LOGF"; for i in $(seq 1 50); do printf 'ok line %s\n' "$i" >> "$LOGF"; done; touch "$LOGF"
live_run
tw "recovery" && grep -a "recovery" "$T/track.log" | grep -aq "up" && ok "world-recovery" || bad "world-recovery" "$(cat "$T/track.log" 2>/dev/null)"
rm -f "$T/track.log"
: > "$LOGF"; for i in $(seq 1 50); do printf 'line %s: No such container: nope\n' "$i" >> "$LOGF"; done; touch "$LOGF"
rm -rf "$T/state/world"; WORLD_TRACK=0 live_run; sleep 0.3
[ ! -s "$T/track.log" ] && ok "world-off" || bad "world-off" "emitted with WORLD_TRACK=0"
rm -f "$T/bin/track"

# ---- summary ----
echo "---"
echo "tests: pass=$pass fail=$fail"
exit $fail
