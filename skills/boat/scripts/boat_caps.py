"""Pure helpers of boat_fallback: boat's caps (hourly 60, daily 200 starts), reset times, the P1 tier rule."""
import json
import os
import re
from datetime import datetime, timedelta

DEFAULT_RUN_STARTS = 13

# P1 runs, the only ones moved to boat (mediatgb ops/ci-preflight.py tier rule): push to main, deploy proofs, merge trains.
P1_BRANCH_PREFIXES = tuple(p for p in os.environ.get("BOAT_P1_BRANCH_PREFIXES", "proof-,train-").split(",") if p)
MONTHS = {m: i for i, m in enumerate(("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"), 1)}


def is_p1(branch, event):
    branch = branch or ""
    return (event == "push" and branch == "main") or branch.startswith(P1_BRANCH_PREFIXES)


def cap_window(reason):
    """Which boat cap paused the job: 'day' (starts in the last 24 hours), 'hour', or None."""
    r = reason or ""
    if "last 24 hours" in r:
        return "day"
    if "last hour" in r:
        return "hour"
    return None


def starts_last_hour(jobs, now, hours=1):
    """Sandbox starts boat counted in the last `hours`, from the jobs' runStartedAt (any repo: the plan is per account).
    /ci lists the latest 200 jobs, so a full day reads as at least 200: no room, which is the safe side."""
    n = 0
    for j in jobs:
        s = j.get("runStartedAt")
        if s and timedelta(0) <= now - parse_iso(s) < timedelta(hours=hours):
            n += 1
    return n


def run_starts(jobs, repo):
    """Starts one run of `repo` takes on boat: the most distinct job names seen in one of its runs."""
    names = {}
    for j in jobs:
        if j.get("repo") == repo and j.get("jobName"):
            names.setdefault(str(j.get("runId")), set()).add(j["jobName"])
    return max((len(v) for v in names.values()), default=DEFAULT_RUN_STARTS) or DEFAULT_RUN_STARTS


def labels_of(runs_on):
    """CI_RUNS_ON value ('"boat"' or '["self-hosted","cachy"]') -> set of runner labels."""
    try:
        v = json.loads(runs_on)
    except (TypeError, ValueError):
        return set()
    return set(v) if isinstance(v, list) else {v}


def parse_iso(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def reset_time(reason, queued_at, now):
    """Boat says "start again at [Nov 15, ]HH:MM UTC". With a date: that time. Without: the next such time after the
    job was queued. No time at all: one hour for the hourly cap, 24 hours for the daily cap (its oldest start ages out
    within a day; boat sends the time in practice)."""
    base = parse_iso(queued_at) if queued_at else now
    m = re.search(r"start again at (?:([A-Z][a-z]{2}) (\d{1,2}), )?(\d{1,2}):(\d{2}) UTC", reason or "")
    if not m:
        return base + timedelta(hours=24) if cap_window(reason) == "day" else now + timedelta(hours=1)
    hour, minute = int(m.group(3)), int(m.group(4))
    if m.group(1) in MONTHS:
        r = base.replace(month=MONTHS[m.group(1)], day=int(m.group(2)), hour=hour, minute=minute, second=0,
                         microsecond=0)
        if r < base - timedelta(days=1):  # Dec -> Jan
            r = r.replace(year=r.year + 1)
        return r
    r = base.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if r < base:
        r += timedelta(days=1)
    return r


def cap_blocked_until(jobs, now):
    """Latest reset still ahead among paused jobs (hourly or daily cap), or None. /ci lists the latest 200 jobs and
    paused ones take places in it, so the starts counted from runStartedAt can read under the cap while it is hit."""
    until = None
    for j in jobs:
        if j.get("state") == "paused" and cap_window(j.get("reason")):
            r = reset_time(j.get("reason"), j.get("queuedAt"), now)
            if r > now and (until is None or r > until):
                until = r
    return until
