"""Boat first, other machines when boat is full (spec 003-boat-fallback).

Run every 2 min (cron): `boat.py ci fallback [--dry-run]`.
When boat pauses CI jobs at the plan limit (60 starts per rolling hour):
- repo with var CI_FALLBACK_RUNS_ON: point CI_RUNS_ON / CI_CONTAINER at the fallback, rerun each paused run in full
  once it is completed, and put the saved values back 15 min after boat's reset when nothing it started is running;
- repo without one: `gh run rerun --failed` 2 min after the reset.
"""
import json
import re
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

STATE = Path.home() / ".local" / "state" / "boat-fallback.json"
LOG = Path.home() / ".local" / "state" / "boat-fallback.log"
RESTORE_MARGIN = timedelta(minutes=15)
RERUN_MARGIN = timedelta(minutes=2)
VARS = ("CI_RUNS_ON", "CI_CONTAINER")


def gh_cli(args):
    try:
        r = subprocess.run(["gh"] + args, capture_output=True, text=True, timeout=60)
    except (subprocess.TimeoutExpired, OSError) as e:
        return 1, str(e)
    return r.returncode, (r.stdout or r.stderr).strip()


def parse_iso(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def reset_time(reason, queued_at, now):
    """Boat says "start again at HH:MM UTC": the next such time after the job was queued."""
    m = re.search(r"start again at (\d{1,2}):(\d{2}) UTC", reason or "")
    if not m:
        return now + timedelta(hours=1)
    base = parse_iso(queued_at) if queued_at else now
    r = base.replace(hour=int(m.group(1)), minute=int(m.group(2)), second=0, microsecond=0)
    if r < base:
        r += timedelta(days=1)
    return r


def load_state(path):
    try:
        st = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        st = {}
    st.setdefault("repos", {})
    st.setdefault("handled", [])
    st.setdefault("later", {})
    return st


def tick(jobs, now, gh=gh_cli, state_path=STATE, log_path=LOG, dry_run=False):
    st = load_state(state_path)
    actions = []

    def save():
        if not dry_run:
            Path(state_path).parent.mkdir(parents=True, exist_ok=True)
            Path(state_path).write_text(json.dumps(st, indent=1))

    def log(msg):
        line = "%s %s%s" % (now.strftime("%Y-%m-%dT%H:%M:%SZ"), "DRY " if dry_run else "", msg)
        actions.append(line)
        if not dry_run:
            Path(log_path).parent.mkdir(parents=True, exist_ok=True)
            with open(log_path, "a") as f:
                f.write(line + "\n")

    def write(args, msg):
        log(msg)
        if dry_run:
            return True
        rc, out = gh(args)
        if rc != 0:
            log("gh failed: %s: %s" % (" ".join(args[:3]), out[:200]))
        return rc == 0

    def get_vars(repo):
        rc, out = gh(["variable", "list", "-R", repo, "--json", "name,value"])
        if rc != 0:
            raise RuntimeError("gh variable list %s failed" % repo)
        try:
            return {v["name"]: v["value"] for v in json.loads(out or "[]")}
        except (ValueError, KeyError, TypeError):
            raise RuntimeError("gh variable list %s: bad output" % repo)

    def set_var(repo, name, value, current):
        if value == current:
            return True
        if value is None:
            return write(["variable", "delete", name, "-R", repo], "%s: delete %s" % (repo, name))
        return write(["variable", "set", name, "-R", repo, "--body", value], "%s: set %s=%s" % (repo, name, value))

    def run_info(repo, run):
        rc, out = gh(["run", "view", str(run), "-R", repo, "--json", "status,startedAt"])
        try:
            return json.loads(out) if rc == 0 else {}
        except ValueError:
            return {}

    def run_status(repo, run):
        return run_info(repo, run).get("status", "unknown")

    # 1. New paused jobs, by repo.
    present = {str(j.get("id")) for j in jobs}
    handled = set(st["handled"]) & present
    fresh = {}
    for j in jobs:
        if j.get("state") == "paused" and str(j.get("id")) not in handled:
            fresh.setdefault(j["repo"], []).append(j)

    for repo, js in list(fresh.items()):
        # Someone (a person or an earlier tick) already reran it: the run's latest attempt started after the pause.
        keep = []
        for run in sorted({str(j["runId"]) for j in js}):
            rjs = [j for j in js if str(j["runId"]) == run]
            started = run_info(repo, run).get("startedAt")
            queued = max(parse_iso(j["queuedAt"]) for j in rjs if j.get("queuedAt")) if any(
                j.get("queuedAt") for j in rjs) else None
            if started and queued and parse_iso(started) > queued:
                handled |= {str(j["id"]) for j in rjs}
            else:
                keep += rjs
        if keep:
            fresh[repo] = keep
        else:
            del fresh[repo]

    for repo, js in fresh.items():
        reset = max(reset_time(j.get("reason"), j.get("queuedAt"), now) for j in js)
        runs = sorted({str(j["runId"]) for j in js})
        try:
            cur = get_vars(repo)
        except RuntimeError as e:
            log(str(e))
            continue
        fb = cur.get("CI_FALLBACK_RUNS_ON")
        if fb:
            until = reset + RESTORE_MARGIN
            rs = st["repos"].get(repo)
            if rs is None and cur.get("CI_RUNS_ON") == fb:
                # Already on the fallback, set by someone else: rerun, but never restore their values.
                rs = st["repos"][repo] = {"saved": None, "set": fb, "since": now.isoformat(),
                                          "until": until.isoformat(), "pending": [], "reran": []}
            if rs is None:
                # State first: a crash after the writes must not lose the values to put back.
                rs = st["repos"][repo] = {"saved": {k: cur.get(k) for k in VARS}, "set": fb,
                                          "since": now.isoformat(), "until": until.isoformat(),
                                          "pending": [], "reran": []}
                save()
                log("%s: boat full until %s, moving CI to %s" % (repo, reset.strftime("%H:%M"), fb))
                set_var(repo, "CI_RUNS_ON", fb, cur.get("CI_RUNS_ON"))
                set_var(repo, "CI_CONTAINER", cur.get("CI_FALLBACK_CONTAINER"), cur.get("CI_CONTAINER"))
            elif until > parse_iso(rs["until"]):
                rs["until"] = until.isoformat()
            rs["pending"] = sorted(set(rs["pending"]) | set(runs))
        else:
            when = (reset + RERUN_MARGIN).isoformat()
            for run in runs:
                key = "%s|%s" % (repo, run)
                queued = max((j["queuedAt"] for j in js if str(j["runId"]) == run and j.get("queuedAt")),
                             default=now.isoformat())
                old = st["later"].get(key) or {}
                st["later"][key] = {"when": max(old.get("when", when), when), "queued": queued}
        handled |= {str(j["id"]) for j in js}

    # 2. Full reruns on the fallback once GitHub shows the run completed.
    for repo, rs in st["repos"].items():
        for run in list(rs["pending"]):
            status = run_status(repo, run)
            if status == "unknown":  # run deleted or unreadable: never block the way back to boat
                log("%s: run %s not readable, dropped" % (repo, run))
                rs["pending"].remove(run)
            elif status == "completed":
                if write(["run", "rerun", run, "-R", repo], "%s: rerun %s in full on the fallback" % (repo, run)):
                    rs["pending"].remove(run)
                    rs["reran"].append(run)

    # 3. Repos without a fallback: rerun the failed jobs after the reset.
    for key, item in list(st["later"].items()):
        if now >= parse_iso(item["when"]):
            repo, run = key.split("|", 1)
            info = run_info(repo, run)
            if not info:
                log("%s: run %s not readable, dropped" % (repo, run))
                del st["later"][key]
                continue
            if info.get("startedAt") and parse_iso(info["startedAt"]) > parse_iso(item["queued"]):
                del st["later"][key]  # someone already reran it
                continue
            if info.get("status") != "completed":
                continue
            if write(["run", "rerun", run, "-R", repo, "--failed"], "%s: boat has room again, rerun %s --failed" % (repo, run)):
                del st["later"][key]

    # 4. Back to boat after the reset.
    for repo, rs in list(st["repos"].items()):
        if now < parse_iso(rs["until"]) or rs["pending"]:
            continue
        # A full rerun on the fallback that is not completed yet (or cannot be read) keeps CI there: its attempt may
        # not have fixed the fallback vars yet. Other runs on the fallback do not block the way back.
        busy = False
        for run in list(rs["reran"]):
            rc, out = gh(["run", "view", str(run), "-R", repo, "--json", "status,startedAt"])
            if rc == 0:
                try:
                    status = json.loads(out).get("status", "unknown")
                except ValueError:
                    status = "unknown"
            else:
                status = "gone" if ("404" in out or "not found" in out.lower()
                                    or "could not find" in out.lower()) else "unknown"
            if status in ("completed", "gone"):  # only a confirmed deleted run stops blocking
                rs["reran"].remove(run)
            else:
                busy = True  # in progress or unreadable (rate limit, network): retry next tick
        if busy:
            continue
        try:
            cur = get_vars(repo)
        except RuntimeError as e:
            log(str(e))
            continue
        if rs["saved"] is None:
            del st["repos"][repo]
            continue
        if cur.get("CI_RUNS_ON") != rs["set"]:
            log("%s: CI_RUNS_ON was changed by someone else, leaving it" % repo)
            del st["repos"][repo]
            continue
        log("%s: boat has room again, moving CI back" % repo)
        ok = True
        for k in VARS:
            ok = set_var(repo, k, rs["saved"].get(k), cur.get(k)) and ok
        if ok:
            del st["repos"][repo]

    st["handled"] = sorted(handled)
    save()
    return actions


def main(dry_run=False):
    import boat
    jobs = boat.api("GET", "/ci").get("jobs", [])
    for line in tick(jobs, now=datetime.now(timezone.utc), dry_run=dry_run):
        print(line)
    return 0
