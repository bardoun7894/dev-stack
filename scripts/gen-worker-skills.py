#!/usr/bin/env python3
"""Regenerate config/worker-skills.json: which skills a lean jdelegate worker may have inlined.

Every unique skill dir in ~/.claude/skills and ~/.claude/skills-parked is classified by Jev
(orchestrator / worker / both); worker + both go in the allowlist. A Jev error leaves the skill out.

  scripts/gen-worker-skills.py            write config/worker-skills.json
  scripts/gen-worker-skills.py --dry-run  print the verdict per skill, write nothing
Env: JDELEGATE_SKILL_DIRS (colon-separated roots), JEV (binary).
"""
import concurrent.futures
import datetime
import json
import os
import re
import subprocess
import sys

HOME = os.path.expanduser("~")
ROOTS = (os.environ.get("JDELEGATE_SKILL_DIRS") or f"{HOME}/.claude/skills:{HOME}/.claude/skills-parked").split(":")
JEV = os.environ.get("JEV") or "jev"
OUT = os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "config", "worker-skills.json")
QUESTION = "Who should use this skill?"
OPTIONS = [
    "orchestrator=planning, KB, research, delegation, deploy, review panels, rituals, media or personal tools",
    "worker=guides how to write, test, debug or polish code while implementing a brief",
    "both=useful to both",
]


# Hand corrections to Jev's verdicts (reviewed 2026-10-02): orchestrator-side pipelines, delegation, release,
# repo-workflow, media and personal tools that Jev called worker/both. Re-applied on every run.
OVERRIDE_OUT = {
    "caveman", "check-project-inbox", "nextjs-storefront-audit", "using-superpowers", "codex", "video-audio-master", "design-check", "design-md", "dogfood", "finishing-a-development-branch", "gh-stack", "github",
    "jev", "kb-dev", "kie-ai", "lean-ctx", "opencode", "receiving-code-review", "requesting-code-review",
    "temporal", "tiktok-business-api", "using-git-worktrees", "writing-skills",
    "davinci-resolve-titles-and-lower-thirds", "davinci-resolve-troubleshooting",
}


OVERRIDE_PREFIX = ("davinci-", "kb-", "video-")


def describe(path):
    """name + description from SKILL.md frontmatter (plain, quoted, or folded > / | blocks)."""
    text = open(path, encoding="utf-8", errors="replace").read()
    m = re.match(r"^---\s*\n(.*?)\n---\s*(\n|$)", text, re.S)
    out, key, block = {}, None, []
    for line in (m.group(1).split("\n") if m else []):
        top = re.match(r"^([A-Za-z_-]+):\s*(.*)$", line)
        if top:
            if key and block:
                out[key] = " ".join(block)
            key, val = top.group(1), top.group(2).strip()
            block = []
            if val in (">", "|", ">-", "|-"):
                continue
            out[key] = val.strip("\"'")
        elif key and line.strip():
            block.append(line.strip())
    if key and block:
        out[key] = " ".join(block)
    return out.get("description", "")


def classify(item):
    name, desc = item
    try:
        r = subprocess.run([JEV, "choice", QUESTION, *OPTIONS, "-s", f"{name}: {desc[:600]}", "-q"],
                           capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        return name, "error"
    verdict = r.stdout.strip()
    return name, (verdict if r.returncode == 0 and verdict in ("orchestrator", "worker", "both") else "error")


def main():
    skills = {}
    for root in ROOTS:
        if not os.path.isdir(root):
            continue
        for name in sorted(os.listdir(root)):
            md = os.path.join(root, name, "SKILL.md")
            if name not in skills and os.path.exists(md):
                skills[name] = describe(md)
    with concurrent.futures.ThreadPoolExecutor(8) as pool:
        verdicts = dict(pool.map(classify, skills.items()))
    for name in sorted(verdicts):
        print(f"{verdicts[name]:13} {name}", file=sys.stderr)
    worker = sorted(n for n, v in verdicts.items() if v in ("worker", "both") and n not in OVERRIDE_OUT and not n.startswith(OVERRIDE_PREFIX))
    if "--dry-run" in sys.argv:
        print(json.dumps(worker))
        return
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        json.dump({"worker": worker, "generated": datetime.date.today().isoformat(), "method": "jev choice"}, f, indent=2)
        f.write("\n")


if __name__ == "__main__":
    main()
