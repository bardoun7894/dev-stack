#!/usr/bin/env python3
"""boat.dev sandbox helper. Stdlib only. The API key is never printed or logged."""
import argparse
import difflib
import io
import json
import os
import re
import subprocess
import sys
import tarfile
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

BASE = os.environ.get("BOAT_API_BASE", "https://boat.dev/api/v1")
KEY_FILE = Path.home() / ".config" / "boat" / "key"
SYNC_MAX = 600
READY_STATES = {"ready", "idle", "running"}
BAD_STATES = {"error", "failed", "archived", "stopped", "deleted"}
SIZES = ["small", "default", "large", "xlarge"]
BLOCKED_REPOS = ()  # none; MEDIA TGB moved to boat CI (owner 2026-11-11), replacing the 2026-11-02 block


class BoatError(Exception):
    pass


def get_key():
    key = os.environ.get("BOAT_API_KEY", "").strip()
    if not key and KEY_FILE.exists():
        key = KEY_FILE.read_text().strip()
    if not key:
        raise BoatError("no API key: set BOAT_API_KEY or create ~/.config/boat/key")
    return key


def _scrub(text, key):
    return text.replace(key, "***") if key and text else text


def _transport(req, timeout):
    """Single network seam; tests replace this. Returns (status, bytes)."""
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def api(method, path, body=None, headers=None, timeout=120):
    key = get_key()
    h = {"Authorization": "Bearer " + key, "Accept": "application/json"}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        h["Content-Type"] = "application/json"
    h.update(headers or {})
    req = urllib.request.Request(BASE + path, data=data, method=method, headers=h)
    try:
        status, raw = _transport(req, timeout)
    except Exception as e:  # network failure
        raise BoatError(_scrub("%s %s failed: %s" % (method, path, e), key))
    try:
        obj = json.loads(raw.decode() or "{}")
    except ValueError:
        obj = {"raw": _scrub(raw.decode(errors="replace")[:500], key)}
    if status >= 400:
        raise BoatError(_scrub("%s %s -> HTTP %s: %s" % (method, path, status, json.dumps(obj)[:500]), key))
    return obj


def put_raw(url, data):
    """PUT bytes to a signed URL (no Authorization header; URL is secret, never printed)."""
    req = urllib.request.Request(url, data=data, method="PUT")
    status, raw = _transport(req, 600)
    if status >= 400:
        raise BoatError("upload failed: HTTP %s" % status)


def out(args, obj, text=None):
    if getattr(args, "json", False):
        print(json.dumps(obj, indent=2))
    elif text is not None:
        print(text)


def create_sandbox(size=None, ttl=3600):
    body = {"ttlSeconds": ttl}
    if size:
        body["type"] = size
    r = api("POST", "/sandboxes", body, {"Idempotency-Key": str(uuid.uuid4())})
    return r["sandbox"]["id"]


def wait_ready(sid, timeout=300):
    end = time.time() + timeout
    while True:
        state = api("GET", "/sandboxes/" + sid).get("sandbox", {}).get("state")
        if state in READY_STATES:
            return state
        if state in BAD_STATES:
            raise BoatError("sandbox %s entered state %s" % (sid, state))
        if time.time() > end:
            raise BoatError("sandbox %s not ready after %ss (state %s)" % (sid, timeout, state))
        time.sleep(2)


def delete_sandbox(sid, wait=True):
    r = api("DELETE", "/sandboxes/" + sid, headers={"X-Ascii-Confirm-Delete": sid})
    op = (r.get("operation") or {}).get("id")
    if wait and op:
        for _ in range(60):
            st = (api("GET", "/deletion-operations/" + op).get("operation") or {}).get("status")
            if st == "completed":
                break
            time.sleep(2)
    return r


def exec_cmd(sid, command, timeout=SYNC_MAX, cwd=None, emit=True):
    """Run a command; return (exitCode, stdout, stderr). Detached+poll above 600 s."""
    base = {"command": command}
    if cwd:
        base["cwd"] = cwd
    if timeout <= SYNC_MAX:
        r = api("POST", "/sandboxes/%s/commands" % sid, dict(base, timeoutSeconds=timeout),
                timeout=timeout + 30)
        so, se = r.get("stdout", ""), r.get("stderr", "")
        if emit:
            sys.stdout.write(so)
            sys.stderr.write(se)
        code = r.get("exitCode")
        if r.get("timedOut") and code is None:
            code = 124
        return (code if code is not None else 1), so, se
    started = api("POST", "/sandboxes/%s/commands" % sid, dict(base, detached=True))
    pid = started["processId"]
    so_off = se_off = 0
    all_o, all_e = [], []
    end = time.time() + timeout
    while True:
        st = api("GET", "/sandboxes/%s/commands/%s?stdoutOffset=%d&stderrOffset=%d" % (sid, pid, so_off, se_off))
        o, e = st.get("stdout", ""), st.get("stderr", "")
        all_o.append(o)
        all_e.append(e)
        if emit:
            sys.stdout.write(o)
            sys.stderr.write(e)
        so_off = st.get("stdoutNextOffset", so_off)
        se_off = st.get("stderrNextOffset", se_off)
        if st.get("more"):
            continue
        if not st.get("running"):
            code = st.get("exitCode")
            return (code if code is not None else 1), "".join(all_o), "".join(all_e)
        if time.time() > end:
            try:
                api("DELETE", "/sandboxes/%s/commands/%s" % (sid, pid))
            except BoatError:
                pass
            return 124, "".join(all_o), "".join(all_e)
        time.sleep(3)


def tracked_files(d):
    r = subprocess.run(["git", "ls-files", "-z"], cwd=d, capture_output=True)
    if r.returncode != 0:
        raise BoatError("%s is not a git checkout (git ls-files failed)" % d)
    names = [n.decode() for n in r.stdout.split(b"\0") if n]
    return [n for n in names if os.path.lexists(os.path.join(d, n)) and not os.path.isdir(os.path.join(d, n))]


def make_tarball(d):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for n in tracked_files(d):
            tf.add(os.path.join(d, n), arcname=n, recursive=False)
    return buf.getvalue()


def push(sid, d):
    d = os.path.abspath(d)
    name = os.path.basename(d.rstrip("/")) or "repo"
    data = make_tarball(d)
    up = api("POST", "/sandboxes/%s/files/upload-url" % sid, {"path": "push.tgz"})
    put_raw(up["url"], data)
    # paths are relative to /home/user (the sandbox work dir)
    code, _, se = exec_cmd(sid, "mkdir -p workspace/%s && tar xzf push.tgz -C workspace/%s && rm push.tgz" % (name, name), emit=False)
    if code != 0:
        raise BoatError("untar failed: " + se[:300])
    return "workspace/" + name


# ---------------- subcommands ----------------

def cmd_ls(a):
    r = api("GET", "/sandboxes")
    sbs = r.get("sandboxes", [])
    if a.json:
        out(a, sbs)
    else:
        for s in sbs:
            print("%s  %-10s  %s  %s" % (s.get("id"), s.get("state"), s.get("type", ""), s.get("createdAt", "")))
        if not sbs:
            print("no sandboxes")
    return 0


def cmd_new(a):
    sid = create_sandbox(a.size, a.ttl)
    try:
        state = wait_ready(sid)
    except BaseException:
        # A VM that never became ready is still billed until its TTL.
        try:
            delete_sandbox(sid, wait=False)
        except Exception:
            pass
        raise
    out(a, {"id": sid, "state": state}, sid)
    return 0


def cmd_status(a):
    s = api("GET", "/sandboxes/" + a.id).get("sandbox", {})
    out(a, s, "%s  %s" % (s.get("id"), s.get("state")))
    return 0


def cmd_exec(a):
    command = " ".join(a.command)
    if not command:
        raise BoatError("no command given (use: exec ID -- CMD)")
    code, so, se = exec_cmd(a.id, command, a.timeout, emit=not a.json)
    if a.json:
        out(a, {"exitCode": code, "stdout": so, "stderr": se})
    return code


def cmd_push(a):
    dest = push(a.id, a.dir)
    out(a, {"dest": dest}, "pushed to ~/" + dest)
    return 0


def cmd_run(a):
    command = " ".join(a.command)
    if not command:
        raise BoatError("no command given (use: run [--push DIR] -- CMD)")
    sid = None
    code = 1
    try:
        sid = create_sandbox(a.size, a.ttl)
        wait_ready(sid)
        cwd = push(sid, a.push) if a.push else None
        code, so, se = exec_cmd(sid, command, a.timeout, cwd=cwd, emit=not a.json)
        if a.json:
            out(a, {"id": sid, "exitCode": code, "stdout": so, "stderr": se})
    except BoatError as e:
        print("boat: " + str(e), file=sys.stderr)
        code = 1
    finally:
        if sid:
            try:
                delete_sandbox(sid)
            except BoatError as e:
                print("boat: WARNING delete of %s failed, remove it manually: %s" % (sid, e), file=sys.stderr)
    return code


def cmd_stop(a):
    api("POST", "/sandboxes/%s/stop" % a.id)
    out(a, {"id": a.id, "stopped": True}, "stopping %s (a billed snapshot is kept; use delete to remove)" % a.id)
    return 0


def cmd_delete(a):
    delete_sandbox(a.id)
    out(a, {"id": a.id, "deleted": True}, "deleted " + a.id)
    return 0


def _age_hours(s):
    c = s.get("createdAt")
    if not c:
        return None
    try:
        t = datetime.fromisoformat(c.replace("Z", "+00:00"))
    except ValueError:
        return None
    return (datetime.now(timezone.utc) - t).total_seconds() / 3600


def cmd_cleanup(a):
    sbs = api("GET", "/sandboxes").get("sandboxes", [])
    victims = []
    for s in sbs:
        age = _age_hours(s)
        if age is None or age >= a.older_than:
            victims.append(s)
    res = {"dryRun": not a.yes, "matched": [s.get("id") for s in victims], "deleted": []}
    for s in victims:
        if a.yes:
            delete_sandbox(s["id"])
            res["deleted"].append(s["id"])
    if a.json:
        out(a, res)
    else:
        verb = "deleted" if a.yes else "would delete (dry run, pass --yes)"
        for s in victims:
            print("%s %s  %s" % (verb, s.get("id"), s.get("createdAt", "")))
        if not victims:
            print("nothing to clean up")
    return 0


WF_RE = re.compile(r"(runs-on:\s*)(\[\s*)?ubuntu-latest(\s*\])?")


def _blocked(repo):
    names = [os.path.basename(os.path.abspath(repo)).lower()]
    r = subprocess.run(["git", "-C", repo, "remote", "get-url", "origin"], capture_output=True, text=True)
    if r.returncode == 0:
        names.append(r.stdout.lower())
    return any(b in n for b in BLOCKED_REPOS for n in names)


def rewrite_workflow(text):
    return WF_RE.sub(lambda m: m.group(1) + "boat", text)


def cmd_ci_enable(a):
    repo = os.path.abspath(a.repo_path)
    if _blocked(repo):
        raise BoatError("refused: repo is in BLOCKED_REPOS")
    wf_dir = Path(repo) / ".github" / "workflows"
    files = [wf_dir / a.workflow] if a.workflow else sorted(list(wf_dir.glob("*.yml")) + list(wf_dir.glob("*.yaml")))
    changed = []
    for f in files:
        if not f.exists():
            raise BoatError("workflow not found: %s" % f)
        old = f.read_text()
        new = rewrite_workflow(old)
        if new != old:
            f.write_text(new)
            changed.append(str(f))
            if not a.json:
                sys.stdout.write("".join(difflib.unified_diff(
                    old.splitlines(True), new.splitlines(True), "a/" + f.name, "b/" + f.name)))
    if a.json:
        out(a, {"changed": changed})
    else:
        print("%d file(s) changed. Nothing committed or pushed. Review, then commit yourself." % len(changed))
        print("One-time: connect GitHub for CI (POST /ci/connect or `boat ci`) and set BOAT_API_KEY as needed.")
    return 0


def cmd_ci_status(a):
    r = subprocess.run(["gh", "run", "list", "-R", a.repo, "--limit", "10", "--json",
                        "databaseId,displayTitle,status,conclusion,workflowName,headBranch,createdAt"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise BoatError("gh run list failed: " + r.stderr.strip()[:300])
    runs = json.loads(r.stdout or "[]")
    if a.json:
        out(a, runs)
    else:
        for x in runs:
            print("%s  %-10s %-10s %-20s %s" % (x["databaseId"], x["status"], x.get("conclusion") or "-",
                                                x["workflowName"], x["displayTitle"][:50]))
    return 0


def build_parser():
    p = argparse.ArgumentParser(prog="boat.py", description="boat.dev sandbox helper")
    sub = p.add_subparsers(dest="cmd", required=True)

    def add(name, fn, **kw):
        sp = sub.add_parser(name, **kw)
        sp.add_argument("--json", action="store_true")
        sp.set_defaults(fn=fn)
        return sp

    add("ls", cmd_ls)
    sp = add("new", cmd_new)
    sp.add_argument("--size", choices=SIZES)
    sp.add_argument("--ttl", type=int, default=3600)
    sp = add("status", cmd_status)
    sp.add_argument("id")
    sp = add("exec", cmd_exec)
    sp.add_argument("id")
    sp.add_argument("--timeout", type=int, default=SYNC_MAX)
    sp.add_argument("command", nargs="*")
    sp = add("push", cmd_push)
    sp.add_argument("id")
    sp.add_argument("dir")
    sp = add("run", cmd_run)
    sp.add_argument("--push")
    sp.add_argument("--size", choices=SIZES)
    sp.add_argument("--ttl", type=int, default=3600)
    sp.add_argument("--timeout", type=int, default=SYNC_MAX)
    sp.add_argument("command", nargs="*")
    sp = add("stop", cmd_stop)
    sp.add_argument("id")
    sp = add("delete", cmd_delete)
    sp.add_argument("id")
    sp = add("cleanup", cmd_cleanup)
    sp.add_argument("--older-than", type=float, default=0, metavar="HOURS")
    sp.add_argument("--yes", action="store_true")
    ci = sub.add_parser("ci")
    cis = ci.add_subparsers(dest="ci_cmd", required=True)
    sp = cis.add_parser("enable")
    sp.add_argument("repo_path")
    sp.add_argument("--workflow")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(fn=cmd_ci_enable)
    sp = cis.add_parser("status")
    sp.add_argument("repo")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(fn=cmd_ci_status)
    return p


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    rest = []
    if "--" in argv:  # everything after the first -- is the remote command, verbatim
        i = argv.index("--")
        argv, rest = argv[:i], argv[i + 1:]
    a = build_parser().parse_args(argv)
    if hasattr(a, "command"):
        a.command = (a.command or []) + rest
    try:
        return a.fn(a)
    except BoatError as e:
        print("boat: " + str(e), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
