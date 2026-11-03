#!/usr/bin/env python3
"""sync-rules-harnesses.py: copy the harness-neutral rules from ~/.claude/CLAUDE.md into every other
agent harness's global instruction file, between <!-- BEGIN claude-shared-rules --> markers.

Idempotent. Each harness keeps its own lean-ctx and jev-first blocks. Stale full copies of the old
rules (OpenCode, Pi) are replaced by the block. Every edited file gets a timestamped .bak-rules-sync copy.

  python3 scripts/sync-rules-harnesses.py              # dry run: writes proposals + diffs to /tmp/rules-sync
  python3 scripts/sync-rules-harnesses.py --apply      # apply
"""
import difflib, os, re, shutil, sys, time

HOME = os.path.expanduser("~")
SRC = f"{HOME}/.claude/CLAUDE.md"
OUT = "/tmp/rules-sync"
APPLY = "--apply" in sys.argv
BEGIN, END = "<!-- BEGIN claude-shared-rules", "<!-- END claude-shared-rules -->"

# (path, create_if_missing)
TARGETS = [
    (f"{HOME}/.codex/AGENTS.md", True),
    (f"{HOME}/.gemini/GEMINI.md", False),
    (f"{HOME}/.config/opencode/AGENTS.md", True),
    (f"{HOME}/.pi/agent/AGENTS.md", False),
    (f"{HOME}/.hermes/HERMES.md", False),
    (f"{HOME}/.continue/rules/claude-shared-rules.md", True),
    (f"{HOME}/.grok/AGENTS.md", True),
]
CAPS = {
    f"{HOME}/.grok/AGENTS.md": 9800,
}

ADAPTER = """You are not Claude Code, but these are the owner's rules for every agent. Translate as you go:
- A slash command or skill name (`/kb-query`, `kb-dev`, `where-to-work`, ...) means: read
  `~/.claude/skills/<name>/SKILL.md` (or `~/.claude/skills-parked/<name>/SKILL.md`) and follow it.
- "Agent tool", "subagent" or a Claude model tier means: dispatch with `jdelegate` as the rules describe.
- Claude hooks (no-poll-guard, kb checks) do not run in this harness. Follow those rules yourself.
- Where a rule names `mcp__...` tools you do not have, skip that source and say so in one line."""


def build_block():
    text = open(SRC).read()
    # Stop before the Claude-specific lean-ctx tail.
    text = text.split("<!-- lean-ctx -->")[0]
    # Drop the auto-generated Claude install state.
    text = re.sub(r"### Auto-generated dev-stack state.*?<!-- END AUTO-GENERATED: dev-stack-state -->\n",
                  "", text, flags=re.S)
    text = re.sub(r"\nOn `📋 RULE OUT OF DATE` alert:.*?\n", "\n", text)
    # Jev-first already has its own synced block in every harness.
    text = re.sub(r"### Jev first — before any model or any bulk reading\n.*?(?=\*\*Parked skills\.\*\*)",
                  "", text, flags=re.S)
    text = text.replace("Apply to every Claude Code session, every project, every prompt.",
                        "Apply to every agent session, every harness, every project, every prompt.")
    text = text.replace("@USER.md is", "Read ~/.claude/USER.md: it is")
    text = re.sub(r"^# Global standing rules\n", "", text).strip("\n")
    stamp = time.strftime("%Y-%m-%d %H:%M", time.localtime(os.path.getmtime(SRC)))
    return (f"{BEGIN} (generated from ~/.claude/CLAUDE.md by dev-stack/scripts/sync-rules-harnesses.py, "
            f"{stamp}; edit CLAUDE.md, never this block) -->\n# Global standing rules\n\n{ADAPTER}\n\n"
            f"{text}\n{END}")


def shrink_longest_section(block):
    body, tail = block.rsplit(f"\n{END}", 1)
    parts = re.split(r"(?m)^(?=##+ )", body)
    if len(parts) <= 1:
        return block
    idx = max(range(1, len(parts)), key=lambda i: len(parts[i]))
    heading = parts[idx].splitlines()[0]
    name = re.sub(r"^#+\s*", "", heading).strip()
    parts[idx] = f"{heading}\n\nfull text: ~/.claude/CLAUDE.md, section {name}\n\n"
    return "".join(parts).rstrip("\n") + f"\n{END}" + tail


def propose(path, block, create):
    if not os.path.exists(path):
        return (block + "\n") if create and os.path.isdir(os.path.dirname(path)) else None
    old = open(path).read()
    if BEGIN in old:
        return re.sub(re.escape(BEGIN) + r".*?" + re.escape(END), lambda _: block, old, count=1, flags=re.S)
    if old.lstrip().startswith("# Global standing rules"):
        # Stale full copy of the old rules: replace it up to the first harness-owned block.
        anchors = [old.find(a) for a in ("## karpathy-guidelines", "<!-- lean-ctx", "<!-- BEGIN jev-first")]
        anchors = [a for a in anchors if a > 0]
        cut = min(anchors) if anchors else len(old)
        return block + "\n\n" + old[cut:].lstrip("\n")
    return block + "\n\n" + old.lstrip("\n")


def main():
    block = build_block()
    os.makedirs(OUT, exist_ok=True)
    open(f"{OUT}/block.md", "w").write(block + "\n")
    stamp = time.strftime("%Y%m%d-%H%M%S")
    for path, create in TARGETS:
        cap = CAPS.get(path)
        tblock = shrink_longest_section(block) if cap else block
        new = propose(path, tblock, create)
        if new is None:
            print(f"skip   {path}")
            continue
        if cap and max(len(new), len(new.encode("utf-8"))) > cap:
            print(f"WARN   {path} exceeds cap ({len(new.encode('utf-8'))} > {cap})")
        old = open(path).read() if os.path.exists(path) else ""
        if new == old:
            print(f"ok     {path}")
            continue
        diff = "".join(difflib.unified_diff(old.splitlines(True), new.splitlines(True), path, path + " (new)"))
        name = path.replace(HOME + "/", "").replace("/", "__")
        open(f"{OUT}/{name}.diff", "w").write(diff)
        add = sum(1 for l in diff.splitlines() if l.startswith("+") and not l.startswith("+++"))
        rem = sum(1 for l in diff.splitlines() if l.startswith("-") and not l.startswith("---"))
        if APPLY:
            if old:
                shutil.copy2(path, f"{path}.bak-rules-sync-{stamp}")
            open(path, "w").write(new)
            print(f"wrote  {path}  (+{add} -{rem})")
        else:
            print(f"would  {path}  (+{add} -{rem})  diff: {OUT}/{name}.diff")


if __name__ == "__main__":
    main()
