#!/usr/bin/env python3
"""Zero-AI digest of a Claude Code session transcript for `/retro session`.

Reads ~/.claude/projects/<slug>/<session>.jsonl and prints a compact report:
token use, tool-call counts, the heaviest tool results, repeated commands,
errors, hook blocks, compactions, and the user's own messages (where
corrections show up). The model reads this digest, never the raw JSONL.

Usage:
  session-digest.py                 # newest session of the current project
  session-digest.py last 3          # the 3 newest sessions of the current project
  session-digest.py <id-prefix>     # a session by id prefix (any project)
  session-digest.py <path.jsonl>
"""
import collections
import glob
import json
import os
import sys

PROJECTS = os.path.expanduser("~/.claude/projects")
CLIP = 160


def project_dir(cwd):
    # Claude Code keys project dirs by the cwd with "/" and "." replaced by "-".
    return os.path.join(PROJECTS, cwd.replace("/", "-").replace(".", "-"))


def resolve(args):
    if args and args[0].endswith(".jsonl"):
        return [args[0]]
    if args and args[0] != "last":
        hits = glob.glob(os.path.join(PROJECTS, "*", args[0] + "*.jsonl"))
        if not hits:
            sys.exit(f"no session matches id prefix {args[0]!r}")
        return sorted(hits, key=os.path.getmtime, reverse=True)[:1]
    n = int(args[1]) if len(args) > 1 else 1
    files = glob.glob(os.path.join(project_dir(os.getcwd()), "*.jsonl"))
    if not files:
        sys.exit(f"no sessions under {project_dir(os.getcwd())}")
    return sorted(files, key=os.path.getmtime, reverse=True)[:n]


def clip(s, n=CLIP):
    s = " ".join(str(s).split())
    return s if len(s) <= n else s[: n - 1] + "…"


def result_text(block):
    c = block.get("content")
    if isinstance(c, list):
        return " ".join(b.get("text", "") for b in c if isinstance(b, dict))
    return str(c or "")


def tool_key(name, inp):
    if name in ("Bash", "ctx_shell") or name.endswith("ctx_shell"):
        return clip(inp.get("command", ""), 100)
    for k in ("file_path", "path", "pattern", "query", "url", "skill"):
        if k in inp:
            return clip(inp[k], 100)
    return clip(json.dumps(inp, ensure_ascii=False), 100)


def digest(path):
    uses = {}  # tool_use_id -> (name, key)
    calls = collections.Counter()
    repeats = collections.Counter()
    heavy, errors, blocks, user_msgs, compactions = [], [], [], [], 0
    tok = collections.Counter()
    title = ""

    for line in open(path, encoding="utf-8", errors="replace"):
        try:
            d = json.loads(line)
        except ValueError:
            continue
        t = d.get("type")
        if t == "ai-title":
            title = d.get("aiTitle", title)
        if t == "system" and "compact" in str(d.get("subtype", "")):
            compactions += 1
        if t == "attachment":
            a = d.get("attachment") or {}
            if a.get("type") in ("hook_blocking_error", "hook_error") or "block" in str(a.get("type", "")):
                blocks.append(clip(f"{a.get('hookName', '')}: {a.get('content') or a.get('stderr', '')}"))
        if t not in ("user", "assistant"):
            continue
        m = d.get("message") or {}
        if t == "assistant":
            u = m.get("usage") or {}
            for k in ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"):
                tok[k] += u.get(k) or 0
        content = m.get("content")
        if isinstance(content, str):
            if t == "user" and not d.get("isMeta") and not content.startswith("<"):
                user_msgs.append(clip(content, 240))
            continue
        for b in content or []:
            bt = b.get("type")
            if bt == "tool_use":
                key = tool_key(b.get("name", ""), b.get("input") or {})
                uses[b.get("id")] = (b.get("name"), key)
                calls[b.get("name")] += 1
                repeats[(b.get("name"), key)] += 1
            elif bt == "tool_result":
                name, key = uses.get(b.get("tool_use_id"), ("?", "?"))
                text = result_text(b)
                heavy.append((len(text), name, key))
                if b.get("is_error"):
                    errors.append(clip(f"{name} {key} -> {text}", 240))
            elif bt == "text" and t == "user" and not d.get("isMeta"):
                txt = b.get("text", "")
                if not txt.startswith("<"):
                    user_msgs.append(clip(txt, 240))

    out = [f"## {os.path.basename(path)}  {title}"]
    out.append(
        "tokens: in={input_tokens} out={output_tokens} cache_read={cache_read_input_tokens} "
        "cache_write={cache_creation_input_tokens}".format(**{k: tok[k] for k in (
            "input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")})
        + f"  compactions={compactions}"
    )
    out.append("tool calls: " + ", ".join(f"{n}×{c}" for n, c in calls.most_common()))
    out.append("\nheaviest tool results (chars):")
    out += [f"  {n:>8}  {name}  {key}" for n, name, key in sorted(heavy, reverse=True)[:8]]
    rep = [(c, n, k) for (n, k), c in repeats.items() if c >= 3]
    if rep:
        out.append("\nrepeated calls (≥3):")
        out += [f"  {c}×  {n}  {k}" for c, n, k in sorted(rep, reverse=True)[:10]]
    if errors:
        out.append(f"\ntool errors ({len(errors)}):")
        out += [f"  {e}" for e in errors[:15]]
    if blocks:
        out.append(f"\nhook blocks ({len(blocks)}):")
        out += [f"  {b}" for b in blocks[:10]]
    out.append(f"\nuser messages ({len(user_msgs)}):")
    out += [f"  - {u}" for u in user_msgs[:40]]
    return "\n".join(out)


if __name__ == "__main__":
    for p in resolve(sys.argv[1:]):
        print(digest(p))
        print()
