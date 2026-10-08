#!/usr/bin/env bash
# server-health.sh — zero-AI health check for the host (MyContabo).
#
# Checks sites, backups, systemd units, pm2, docker, cron logs, disk, and
# chkrootkit. Sends one Telegram message per finding (deduped for 6h), one
# "recovered" message when a finding clears, and a daily digest on --summary.
#
# Env (all optional):
#   STATE_DIR     default /var/lib/server-health
#   ENV_FILE      default /root/tokyo/.env  (must define TELEGRAM_BOT_TOKEN, TELEGRAM_USER_ID)
#   BACKUP_DIRS   default /root/db-backups  (colon-separated)
#   NGINX_CONF_DIR   default /etc/nginx/sites-enabled
#   VAR_LOG_CHKROOTKIT  default /var/log/chkrootkit/log.today
#   DOCKER_IGNORE  regex (default '^(ostudio-dev-|board-test-)|_[a-z]+$')
#
# Flags:
#   --dry-run   print findings to stdout instead of sending Telegram
#   --rebaseline  rewrite $STATE_DIR/chkrootkit.baseline from the current log
#   --summary   send the daily digest (all current findings, or "all green")
#
# Exit 0 always unless the script itself breaks.

set -u
PATH="${PATH:-/usr/bin:/bin}"

STATE_DIR="${STATE_DIR:-/var/lib/server-health}"
ENV_FILE="${ENV_FILE:-/root/tokyo/.env}"
BACKUP_DIRS="${BACKUP_DIRS:-/root/db-backups}"
NGINX_CONF_DIR="${NGINX_CONF_DIR:-/etc/nginx/sites-enabled}"
VAR_LOG_CHKROOTKIT="${VAR_LOG_CHKROOTKIT:-/var/log/chkrootkit/log.today}"
DOCKER_IGNORE="${DOCKER_IGNORE:-^(ostudio-dev-|board-test-)|_[a-z]+$}"

DRY_RUN=0
SUMMARY=0
REBASELINE=0
for a in "$@"; do
  case "$a" in
    --dry-run) DRY_RUN=1 ;;
    --summary) SUMMARY=1 ;;
    --rebaseline) REBASELINE=1 ;;
    --help|-h)
      sed -n '2,30p' "$0"; exit 0 ;;
  esac
done

mkdir -p "$STATE_DIR" 2>/dev/null || true
DEDUPE_FILE="$STATE_DIR/findings.sent"
REC_FILE="$STATE_DIR/recoveries.sent"
PM2_PREVIOUS="$STATE_DIR/pm2-restarts.previous"
DOCKER_PREVIOUS="$STATE_DIR/docker-running.previous"

# Each check appends lines to FINDINGS as "CHECK: detail".
FINDINGS=""

add() { FINDINGS="${FINDINGS}${1}: ${2}
"; }

# Portable (GNU first, BSD fallback) stat helpers.
file_mtime() { stat -c %Y "$1" 2>/dev/null || stat -f %m "$1" 2>/dev/null || echo 0; }
file_size() { stat -c %s "$1" 2>/dev/null || stat -f %z "$1" 2>/dev/null || echo 0; }

# --- Telegram ---
send_telegram() {
  local msg="$1"
  if [ "$DRY_RUN" = "1" ]; then
    printf '%s\n' "$msg"
    return 0
  fi
  [ -r "$ENV_FILE" ] || return 0
  local token chatid
  token=$(. "$ENV_FILE" 2>/dev/null && printf '%s' "${TELEGRAM_BOT_TOKEN:-}")
  chatid=$(. "$ENV_FILE" 2>/dev/null && printf '%s' "${TELEGRAM_USER_ID:-}")
  [ -n "$token" ] && [ -n "$chatid" ] || return 0
  TEK="$token" CID="$chatid" MSG="$msg" python3 -c '
import json, os
print(json.dumps({"chat_id": os.environ["CID"], "text": os.environ["MSG"]}))
' | curl -sS -H "Content-Type: application/json" -X POST \
    --data-binary @- "https://api.telegram.org/bot${TEK}/sendMessage" >/dev/null
}

# Returns 0 if finding already sent within 6h (skip); 1 if newly sent.
should_send() {
  local key="$1" now last
  now=$(date +%s)
  last=$(awk -F'\t' -v k="$key" '$2 == k {t=$1} END {print t}' "$DEDUPE_FILE" 2>/dev/null)
  if [ -z "$last" ]; then
    printf '%s\t%s\n' "$now" "$key" >> "$DEDUPE_FILE"
    return 1
  fi
  if [ $((now - last)) -ge 21600 ]; then
    printf '%s\t%s\n' "$now" "$key" >> "$DEDUPE_FILE"
    return 1
  fi
  return 0
}

# --- a. sites ---
check_sites() {
  local f names=""
  [ -d "$NGINX_CONF_DIR" ] || return 0
  for f in "$NGINX_CONF_DIR"/*.conf; do
    [ -e "$f" ] || continue
    # extract every "server_name NAME" line: capture the entire remaining line, split on whitespace.
    while IFS= read -r line; do
      [ -z "$line" ] && continue
      line=${line#*server_name}
      line=${line## }
      # strip trailing semicolons
      line=${line%;}
      for w in $line; do
        case "$w" in
          _|localhost|"") continue ;;
        esac
        if printf '%s' "$w" | grep -Eq '^[*~]'; then continue; fi
        if printf '%s' "$w" | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$|^::1$'; then continue; fi
        if printf '%s' "$w" | grep -Eq '^\['; then continue; fi
        names="$names $w"
      done
    done < <(grep -E '^[[:space:]]*server_name[[:space:]]+' "$f" 2>/dev/null)
  done
  [ -z "$names" ] && return 0
  local results
  results=$(printf '%s\n' $names | sort -u | xargs -P8 -n1 sh -c '
    getent ahosts "$1" 2>/dev/null | grep -q . || exit 0
    code=$(curl -s -o /dev/null -m 10 -w "%{http_code}" "https://$1/" 2>/dev/null)
    case "$code" in 000|5*) printf "%s %s\n" "$1" "$code" ;; esac
  ' _)
  local name code
  while IFS=' ' read -r name code; do
    [ -z "$code" ] && continue
    add "site" "$name $code"
  done <<<"$results"
}

# --- b. backups ---
check_backups() {
  local dirs d f base prefix idx now key ts sz psz age_h
  now=$(date +%s)
  IFS=: read -r -a dirs <<<"$BACKUP_DIRS"
  idx=$(mktemp)
  for d in "${dirs[@]}"; do
    [ -d "$d" ] || continue
    for f in "$d"/*; do
      [ -f "$f" ] || continue
      base=${f##*/}
      prefix=$(printf '%s' "$base" | sed -E 's/\.(sql\.gz|sql|tar\.gz|tgz|tar|gz|dump)$//; s/[-_][0-9]{4}[-_][0-9]{2}[-_][0-9]{2}.*$//; s/[-_][0-9]{8}.*$//')
      printf '%s|%s\t%s\t%s\n' "$d" "$prefix" "$(file_mtime "$f")" "$(file_size "$f")"
    done
  done | sort -t$'\t' -k1,1 -k2,2nr > "$idx"
  # one line per prefix: key, newest mtime, newest size, previous size (-1 if none)
  while IFS=$'\t' read -r key ts sz psz; do
    [ -z "$key" ] && continue
    prefix=${key#*|}
    age_h=$(( (now - ts) / 3600 ))
    if [ "$age_h" -gt 36 ]; then
      # retired prefixes (nothing for a week) stop alerting
      [ "$age_h" -le 168 ] && add "backup" "$prefix missing (newest file ${age_h}h old)"
    elif [ "$sz" -lt 1024 ]; then
      add "backup" "$prefix ${sz} bytes (under 1KB)"
    elif [ "$psz" -gt 0 ] && [ $(( sz * 100 / psz )) -lt 50 ]; then
      add "backup" "$prefix ${sz} bytes (less than 50% of previous ${psz})"
    fi
  done < <(awk -F'\t' '
    $1 != k { if (k != "") print k "\t" ts "\t" sz "\t" psz; k=$1; ts=$2; sz=$3; psz=-1; n=1; next }
    n == 1 { psz=$3; n=2 }
    END { if (k != "") print k "\t" ts "\t" sz "\t" psz }' "$idx")
  rm -f "$idx"
}

# --- c. units ---
check_units() {
  local line
  while IFS= read -r line; do
    [ -z "$line" ] && continue
    add "unit" "$line"
  done < <(systemctl --failed --no-legend --plain 2>/dev/null)
}

# --- d. pm2 ---
check_pm2() {
  local jlist
  jlist=$(pm2 jlist 2>/dev/null)
  [ -z "$jlist" ] && return 0
  local tmp; tmp=$(mktemp)
  printf '%s' "$jlist" | python3 -c '
import json, sys
text = sys.stdin.read()
lines = text.split("\n")
for i, l in enumerate(lines):
    if l.lstrip().startswith("["):
        text = "\n".join(lines[i:])
        break
try:
    data = json.loads(text)
except Exception:
    data = []
for p in data:
    env = p.get("pm2_env") or {}
    print("%s\t%s\t%d" % (p.get("name", "?"), env.get("status", ""), int(env.get("restart_time") or 0)))
' > "$tmp" 2>/dev/null
  local name status rt prev_v
  while IFS=$'\t' read -r name status rt; do
    [ -z "$name" ] && continue
    if [ "$status" != "online" ]; then
      add "pm2" "$name status=$status restarts=$rt"
      continue
    fi
    prev_v=$(awk -F'\t' -v n="$name" '$2==n {print $1; exit}' "$PM2_PREVIOUS" 2>/dev/null)
    if [ -z "${prev_v:-}" ]; then
      :
    elif [ "$((rt - prev_v))" -gt 20 ]; then
      add "pm2" "$name restarts=$rt (was $prev_v)"
    fi
  done < "$tmp"
  awk -F'\t' '{printf "%s\t%s\n", $3, $1}' "$tmp" > "$PM2_PREVIOUS.new" 2>/dev/null
  mv "$PM2_PREVIOUS.new" "$PM2_PREVIOUS" 2>/dev/null || true
  rm -f "$tmp"
}

# --- e. docker ---
check_docker() {
  local cur prev name
  cur=$(docker ps --format '{{.Names}}' 2>/dev/null | sort -u)
  prev=$(cat "$DOCKER_PREVIOUS" 2>/dev/null | sort -u)
  if [ -n "$prev" ]; then
    while IFS= read -r name; do
      [ -z "$name" ] && continue
      printf '%s\n' "$cur" | grep -qx "$name" && continue
      if printf '%s' "$name" | grep -Eq "$DOCKER_IGNORE"; then continue; fi
      add "docker" "$name not running"
    done <<<"$prev"
  fi
  printf '%s\n' "$cur" > "$DOCKER_PREVIOUS"
}

# --- f. cron logs ---
check_cron_logs() {
  local crontab tfile mtime now age_s last_lines line hits last_line short
  crontab=$(crontab -l 2>/dev/null) || return 0
  while IFS= read -r tfile; do
    [ -z "$tfile" ] && continue
    [ -f "$tfile" ] || continue
    mtime=$(file_mtime "$tfile")
    now=$(date +%s)
    age_s=$((now - mtime))
    [ "$age_s" -gt 7200 ] && continue
    last_lines=$(tail -n 50 "$tfile" 2>/dev/null)
    hits=0
    last_line=""
    while IFS= read -r line; do
      [ -z "$line" ] && continue
      if printf '%s' "$line" | grep -Eiq 'error|fail|exception|No such container|ENOENT|denied|Traceback'; then
        hits=$((hits+1))
        last_line="$line"
      fi
    done <<<"$last_lines"
    if [ "$hits" -ge 20 ]; then
      short=$(printf '%s' "$last_line" | cut -c1-160)
      add "cronlog" "$tfile last line: $short"
    fi
  done < <(printf '%s\n' "$crontab" | grep -Eo '>>[[:space:]]*/[^[:space:]]+' | sed -E 's/^>>[[:space:]]*//')
}

# --- g. disk ---
check_disk() {
  local line fs mp use dev
  while IFS= read -r line; do
    dev=$(awk '{print $1}' <<<"$line")
    mp=$(awk '{print $6}' <<<"$line")
    case "$dev" in
      tmpfs|overlay|devfs|*loop*|squashfs) continue ;;
    esac
    use=$(awk '{print $5}' <<<"$line" | tr -d '%')
    if [ "${use:-0}" -ge 85 ]; then
      add "disk" "$mp ${use}% (df -P)"
    fi
  done < <(df -P 2>/dev/null | tail -n +2)
}

# --- h. chkrootkit ---
# Reports only paths not in $STATE_DIR/chkrootkit.baseline (seeded on first run).
check_chkrootkit() {
  [ -f "$VAR_LOG_CHKROOTKIT" ] || return 0
  local pth base="$STATE_DIR/chkrootkit.baseline" cur
  cur=$(awk '
    /^(Searching for|Checking)/ { inw = 0; next }
    /WARNING/ { inw = 1; next }
    inw && /^\// && !/lstat\(\/tmp\/runc-process/ { print }
  ' "$VAR_LOG_CHKROOTKIT" | grep -Ev '^/tmp/' | sort -u)
  if [ "$REBASELINE" = "1" ] || [ ! -f "$base" ]; then
    printf '%s\n' "$cur" | sed '/^$/d' > "$base"
    return 0
  fi
  while IFS= read -r pth; do
    [ -z "$pth" ] && continue
    add "chkrootkit" "$pth"
  done < <(printf '%s\n' "$cur" | comm -23 - "$base")
}

# --- run all checks ---
check_sites
check_backups
check_units
check_pm2
check_docker
check_cron_logs
check_disk
check_chkrootkit

# --- emit ---
emit() {
  if [ -z "$FINDINGS" ]; then
    [ "$SUMMARY" = "1" ] && send_telegram "[server-health] all green ($(hostname -s 2>/dev/null || echo host))"
    return 0
  fi
  if [ "$SUMMARY" = "1" ]; then
    n=$(grep -c . <<<"$FINDINGS")
    send_telegram "[server-health] $n findings ($(hostname -s 2>/dev/null || echo host))
${FINDINGS}"
    return 0
  fi
  # dedupe: send only findings not sent in last 6h
  while IFS= read -r finding; do
    [ -z "$finding" ] && continue
    if should_send "$finding"; then continue; fi
    send_telegram "[server-health] ${finding}"
  done <<<"$FINDINGS"

  # recovery: a previously-sent finding that no longer appears
  if [ -s "$DEDUPE_FILE" ]; then
    local key
    while IFS= read -r key; do
      [ -z "$key" ] && continue
      printf '%s\n' "$FINDINGS" | grep -Fxq -- "$key" && continue
      send_telegram "[server-health] recovered: ${key}"
      awk -F'\t' -v k="$key" '$2 != k' "$DEDUPE_FILE" > "$DEDUPE_FILE.new" && mv "$DEDUPE_FILE.new" "$DEDUPE_FILE"
    done < <(awk -F'\t' '{print $2}' "$DEDUPE_FILE" | sort -u)
  fi
}

emit
exit 0
