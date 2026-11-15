"""Boat first, other machines when boat is full (spec 003-boat-fallback).

Run every 2 min (cron): `boat.py ci fallback [--dry-run]`.
When boat pauses CI jobs at the plan limit (60 starts per rolling hour):
- repo with var CI_FALLBACK_RUNS_ON: point CI_RUNS_ON / CI_CONTAINER at the fallback, rerun each paused run in full
  once it is completed, and put the saved values back 15 min after boat's reset once its reruns have started;
- every tick, for a repo with a fallback whose CI is on boat: cancel and rerun in full the runs still waiting
  unstarted on the fallback, within boat's free starts (D8);
- repo without one: `gh run rerun --failed` 2 min after the reset.
Only P1 runs (push to main, head branch proof-* or train-*) are moved to boat; while a paused job says boat's hourly or
daily cap is still on, nothing is moved.
"""
import json
import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

from boat_caps import (  # noqa: F401  (re-exported: tests and callers use bf.<name>)
    MONTHS, P1_BRANCH_PREFIXES, cap_blocked_until, cap_window, is_p1, labels_of, parse_iso, reset_time, run_starts,
    starts_last_hour)

STATE = Path.home() / ".local" / "state" / "boat-fallback.json"
LOG = Path.home() / ".local" / "state" / "boat-fallback.log"
RESTORE_MARGIN = timedelta(minutes=15)
RERUN_MARGIN = timedelta(minutes=2)
VARS = ("CI_RUNS_ON", "CI_CONTAINER")
# Moving stranded runs back (D8): boat's plan has 60 starts per rolling hour and 200 per rolling 24 h (one per job;
# 11-14 log: "You used all 200 sandbox starts included in the last 24 hours"). Env overrides after a plan change.
# Some starts stay free for new pushes.
STARTS_PER_HOUR = int(os.environ.get("BOAT_STARTS_PER_HOUR", "60"))
STARTS_PER_DAY = int(os.environ.get("BOAT_STARTS_PER_DAY", "200"))
STARTS_KEPT_FREE = 15
MOVE_TIMEOUT = timedelta(minutes=30)
MAX_RUN_CHECKS = 20  # job lists read per repo per tick while looking for stranded runs
QUEUED = ("queued", "pending", "waiting", "requested")


def gh_cli(args):
    try:
        r = subprocess.run(["gh"] + args, capture_output=True, text=True, timeout=60)
    except (subprocess.TimeoutExpired, OSError) as e:
        return 1, str(e)
    return r.returncode, (r.stdout or r.stderr).strip()


def load_state(path):
    try:
        st = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        st = {}
    st.setdefault("repos", {})
    st.setdefault("handled", [])
    st.setdefault("later", {})
    st.setdefault("moving", {})
    st.setdefault("fallback_repos", [])  # repos the watcher ever moved: checked for stranded runs even without boat jobs
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
        rc, out = gh(["run", "view", str(run), "-R", repo, "--json", "status,startedAt,attempt"])
        try:
            return json.loads(out) if rc == 0 else {}
        except ValueError:
            return {}

    def gh_json(args):
        rc, out = gh(args)
        if rc != 0:
            return None
        try:
            return json.loads(out or "null")
        except ValueError:
            return None

    def newest_run(repo, branch, workflow, event):
        """Newest run of the same workflow and event on the branch (other workflows do not supersede it)."""
        cmd = ["run", "list", "-R", repo, "--branch", branch, "--limit", "1", "--json", "databaseId"]
        if workflow:
            cmd += ["--workflow", str(workflow)]
        if event:
            cmd += ["--event", event]
        rows = gh_json(cmd)
        return str(rows[0]["databaseId"]) if rows else None

    def unstarted_on(repo, run, labels):
        """No job carrying the fallback's labels has started (a finished preflight or a skipped job does not count).
        Jobs on other runners (light jobs: preflight, build, checks) are ignored: the full rerun repeats them."""
        data = gh_json(["api", "repos/%s/actions/runs/%s/jobs" % (repo, run)]) or {}
        rjobs = [j for j in (data.get("jobs") or []) if labels <= set(j.get("labels") or [])]
        if not rjobs:
            return False
        for j in rjobs:
            if j.get("status") == "in_progress":
                return False
            if j.get("status") == "completed" and not (
                    str(j.get("name", "")).startswith("preflight") or j.get("conclusion") == "skipped"):
                return False
        return any(j.get("status") != "completed" for j in rjobs)

    def room_for(repo):
        """Runs of `repo` boat can take now, keeping STARTS_KEPT_FREE. Moved runs not rerun yet, or rerun but not
        started on boat, are not in runStartedAt: their own start counts are added as used."""
        per_run = run_starts(jobs, repo)
        if cap_blocked_until(jobs, now):
            return 0, per_run
        pending = sum(m.get("starts", per_run) for m in st["moving"].values())
        free = min(STARTS_PER_HOUR - starts_last_hour(jobs, now), STARTS_PER_DAY - starts_last_hour(jobs, now, 24))
        return max(0, (free - STARTS_KEPT_FREE - pending) // per_run), per_run

    def move_stranded(repo, labels):
        """D8: CI is back on boat; runs queued on the fallback keep its vars. Cancel the oldest ones that have not
        started (newest run per branch only) while boat has room, and rerun them in full on later ticks."""
        if not labels:
            return
        room, per_run = room_for(repo)
        if room <= 0:
            return
        rows = gh_json(["run", "list", "-R", repo, "--limit", "100",
                        "--json", "databaseId,status,headBranch,createdAt,workflowDatabaseId,event"]) or []
        # newest per branch, workflow and event: a run of another workflow or event does not supersede this one
        newest = {}
        for r in rows:
            k = (r.get("headBranch"), r.get("workflowDatabaseId"), r.get("event"))
            if r.get("createdAt", "") > newest.get(k, ""):
                newest[k] = r.get("createdAt", "")
        # in_progress: a run whose preflight finished is in_progress; unstarted_on decides whether it can move
        queued = sorted((r for r in rows if r.get("status") in QUEUED + ("in_progress",)
                         and is_p1(r.get("headBranch"), r.get("event"))
                         and r.get("createdAt") == newest.get((r.get("headBranch"), r.get("workflowDatabaseId"), r.get("event")))),
                        key=lambda r: r.get("createdAt", ""))
        moved = checked = 0
        for r in queued:
            if moved >= room or checked >= MAX_RUN_CHECKS:
                break
            run = str(r["databaseId"])
            key = "%s|%s" % (repo, run)
            if key in st["moving"]:
                continue
            checked += 1
            if not unstarted_on(repo, run, labels):
                continue
            # force-cancel: a plain cancel leaves the always() ci-ok job queued for a fallback runner.
            if write(["api", "-X", "POST", "repos/%s/actions/runs/%s/force-cancel" % (repo, run)],
                     "%s: run %s has not started on the fallback, moving it to boat" % (repo, run)):
                st["moving"][key] = {"since": now.isoformat(), "branch": r.get("headBranch"), "starts": per_run,
                                     "wf": r.get("workflowDatabaseId"), "event": r.get("event")}
                moved += 1

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
                if repo not in st["fallback_repos"]:
                    st["fallback_repos"].append(repo)
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
            info = run_info(repo, run)
            status = info.get("status", "unknown")
            if status == "unknown":  # run deleted or unreadable: never block the way back to boat
                log("%s: run %s not readable, dropped" % (repo, run))
                rs["pending"].remove(run)
            elif status == "completed":
                before = info.get("attempt")
                if write(["run", "rerun", run, "-R", repo], "%s: rerun %s in full on the fallback" % (repo, run)):
                    rs["pending"].remove(run)
                    rs["reran"].append(run)
                    # None: attempt unreadable before the rerun, so step 4 waits for the run to complete instead.
                    rs.setdefault("reran_attempt", {})[run] = before if isinstance(before, int) else None

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
        # A full rerun on the fallback keeps CI there until its new attempt has started (or cannot be read): GitHub
        # fixes vars when the attempt starts, so a started rerun finishes on the fallback while CI goes back to boat.
        # Waiting for it to complete kept boat idle for hours behind a laptop queue. Other runs do not block.
        busy = False
        before = rs.setdefault("reran_attempt", {})
        for run in list(rs["reran"]):
            rc, out = gh(["run", "view", str(run), "-R", repo, "--json", "status,startedAt,attempt"])
            attempt = None
            if rc == 0:
                try:
                    info = json.loads(out)
                    status, attempt = info.get("status", "unknown"), info.get("attempt")
                except ValueError:
                    status = "unknown"
            else:
                status = "gone" if ("404" in out or "not found" in out.lower()
                                    or "could not find" in out.lower()) else "unknown"
            # GitHub's attempt number, not clocks: the new attempt exists once it is above the one before the rerun.
            # Right after the rerun the run can still read "completed" (old attempt), so that alone never unblocks.
            # Run missing from the map (state from before this field): that rerun began long ago.
            # Baseline None (unreadable at rerun time): wait for the run to complete, like the old rule.
            if run not in before:
                done = status != "unknown"
            elif before[run] is None:
                done = status == "completed"
            else:
                done = isinstance(attempt, int) and attempt > before[run]
            if status == "gone" or done:  # only a confirmed deleted run stops blocking
                rs["reran"].remove(run)
                before.pop(run, None)
            else:
                busy = True  # rerun attempt not started yet, or unreadable (rate limit, network): retry next tick
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

    # 5. Moved runs: once the cancel has landed, rerun in full so the new attempt picks boat's vars. A rerun run stays
    #    listed (and counted against boat's room) until boat shows one of its jobs started, or MOVE_TIMEOUT passed.
    for key, item in list(st["moving"].items()):
        repo, run = key.split("|", 1)
        if not item.get("reran") and not is_p1(item.get("branch"), item.get("event")):
            log("%s: run %s on %s is not P1, not moved to boat" % (repo, run, item.get("branch")))
            del st["moving"][key]
            continue
        if item.get("reran"):
            if any(str(j.get("runId")) == run and j.get("runStartedAt") for j in jobs) or (
                    now - parse_iso(item["reran"]) > MOVE_TIMEOUT):
                del st["moving"][key]
            continue
        info = run_info(repo, run)
        if not info:  # unreadable (gh error, rate limit): keep the move until MOVE_TIMEOUT, never drop it early
            if now - parse_iso(item["since"]) > MOVE_TIMEOUT:
                log("%s: run %s not readable for %d min, dropped from the move" % (
                    repo, run, MOVE_TIMEOUT.total_seconds() // 60))
                del st["moving"][key]
            continue
        if info.get("status") != "completed":
            if now - parse_iso(item["since"]) > MOVE_TIMEOUT:
                log("%s: run %s still not cancelled after %d min, left alone" % (
                    repo, run, MOVE_TIMEOUT.total_seconds() // 60))
                del st["moving"][key]
            continue
        newest = newest_run(repo, item["branch"], item.get("wf"), item.get("event"))
        if newest is not None and newest != run:
            log("%s: run %s was replaced by %s on %s, not rerun" % (repo, run, newest, item["branch"]))
            del st["moving"][key]
            continue
        if write(["run", "rerun", run, "-R", repo], "%s: rerun %s in full on boat" % (repo, run)):
            item["reran"] = now.isoformat()

    # 6. Runs stranded on the fallback while CI is on boat (D8): every tick, not only right after a restore, so runs
    #    left there by a restore without room (or by an older watcher) still move once boat has room.
    for repo in sorted({j.get("repo") for j in jobs if j.get("repo")} | set(st["fallback_repos"])):
        if repo in st["repos"] or room_for(repo)[0] <= 0:  # no room: skip the API calls
            continue
        try:
            cur = get_vars(repo)
        except RuntimeError as e:
            log(str(e))
            continue
        fb = cur.get("CI_FALLBACK_RUNS_ON")
        if fb and cur.get("CI_RUNS_ON") != fb:
            # CI_HEAVY_RUNS_ON: the laptop label set of the heavy jobs (mediatgb ci.yml); light jobs run elsewhere.
            move_stranded(repo, labels_of(cur.get("CI_HEAVY_RUNS_ON") or fb))

    st["handled"] = sorted(handled)
    save()
    return actions


def main(dry_run=False):
    import boat
    jobs = boat.api("GET", "/ci").get("jobs", [])
    for line in tick(jobs, now=datetime.now(timezone.utc), dry_run=dry_run):
        print(line)
    return 0
