#!/bin/bash
# install-guard.sh — PreToolUse Bash / ctx_shell supply-chain guard.
#   - Hard DENY: piping curl/wget output straight into sh/bash/zsh/python/node.
#   - Interactive ASK: installing new packages (npm/pnpm/yarn/bun/pip/uv/cargo/go/brew/gem),
#     running remote runners (npx non-local, pnpx, bunx, uvx, pipx), or `claude mcp add`.
#   - Silent ALLOW: lockfile installs (`npm ci`, `npm install`, `pnpm install`, `uv sync`),
#     editable/local requirements (`pip install -e .`, `pip install -r requirements.txt`),
#     local project bins (`npx <bin>` when `$cwd/node_modules/.bin/<bin>` exists), and read-only cmds.
# Emergency owner bypass: INSTALL_GUARD_SKIP=1 in the hook's own environment.
set -u

[ "${INSTALL_GUARD_SKIP:-}" = "1" ] && exit 0

in=""
[ -t 0 ] || in=$(cat 2>/dev/null || true)
[ -n "$in" ] || exit 0


out=$(printf '%s' "$in" | python3 -c '
import json, os, re, shlex, sys

try:
    payload = json.load(sys.stdin)
except Exception:
    sys.exit(0)

ti = payload.get("tool_input") if isinstance(payload, dict) else None
cmd = (ti.get("command") if isinstance(ti, dict) else None) or ""
cwd = (payload.get("cwd") if isinstance(payload, dict) else None) or ""
if not isinstance(cmd, str) or not cmd.strip():
    sys.exit(0)

def emit(decision: str, reason: str) -> None:
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision,
            "permissionDecisionReason": reason,
        }
    }))
    sys.exit(0)

def strip_heredocs(text: str) -> str:
    out, skip_term = [], None
    heredoc_re = re.compile(r"<<-?\s*[\x27\x22]?([A-Za-z_][A-Za-z0-9_]*)[\x27\x22]?")
    exec_consumer_re = re.compile(r"(^|[\s;&|(`$])(bash|sh|zsh|dash|ksh|python3?|node|deno|eval|source|ssh|sudo|env|xargs|exec)(?=[\s;&|)]|$)")
    for line in text.splitlines():
        if skip_term is not None:
            if line.strip() == skip_term:
                skip_term = None
            continue
        out.append(line)
        code = strip_comment(line)
        if "<<<" not in code and not exec_consumer_re.search(code):
            for m in heredoc_re.finditer(code):
                q = None
                for ch in code[:m.start()]:
                    if q is None and ch in "\x27\x22":
                        q = ch
                    elif ch == q:
                        q = None
                if q is None:
                    skip_term = m.group(1)
                    break
    return "\n".join(out)

def strip_comment(line: str) -> str:
    sq = dq = esc = False
    for idx, ch in enumerate(line):
        if esc:
            esc = False
            continue
        if ch == "\\" and not sq:
            esc = True
            continue
        if ch == "\x27" and not dq:
            sq = not sq
        elif ch == "\x22" and not sq:
            dq = not dq
        elif ch == "#" and not sq and not dq and (idx == 0 or line[idx - 1].isspace()):
            return line[:idx]
    return line

def split_top(text: str, sep_chars: str):
    parts, buf = [], []
    sq = dq = esc = False
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if esc:
            buf.append(ch); esc = False; i += 1; continue
        if ch == "\\" and not sq:
            buf.append(ch); esc = True; i += 1; continue
        if ch == "\x27" and not dq:
            sq = not sq; buf.append(ch); i += 1; continue
        if ch == "\x22" and not sq:
            dq = not dq; buf.append(ch); i += 1; continue
        if not sq and not dq:
            if text[i:i+2] in ("&&", "||") and ("&" in sep_chars or "|" in sep_chars):
                parts.append(("".join(buf), text[i:i+2])); buf = []; i += 2; continue
            if ch in sep_chars:
                parts.append(("".join(buf), ch)); buf = []; i += 1; continue
        buf.append(ch); i += 1
    parts.append(("".join(buf), ""))
    return parts

WRAPPER_VAL_FLAGS = {"-u", "-C", "-p", "-t"}
SSH_VAL_FLAGS = {"-o", "-i", "-p", "-l", "-F", "-J", "-L", "-R", "-D", "-E", "-W", "-b", "-c", "-e", "-m"}
NPM_VAL_FLAGS = {"--loglevel", "--prefix", "--registry", "--cache", "--tag", "--workspace", "-w"}
FETCH_SUB_RE = re.compile(r"^\s*[({]?\s*(sudo\s+)?(\S*/)?(curl|wget)\b")

def in_lockfile(pkg: str, root: str) -> bool:
    pat = re.compile(r"(?<![\w.-])" + re.escape(pkg) + r"(?![\w.-])")
    for name in ("package-lock.json", "pnpm-lock.yaml", "yarn.lock", "bun.lock"):
        try:
            with open(os.path.join(root, name), encoding="utf-8", errors="replace") as fh:
                if pat.search(fh.read()):
                    return True
        except OSError:
            pass
    return False

def unwrap_tokens(toks):
    i, n = 0, len(toks)
    while i < n:
        t = toks[i]
        if "=" in t and not t.startswith("-") and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", t):
            i += 1; continue
        if t in ("sudo", "env", "nice"):
            i += 1
            while i < n and toks[i].startswith("-"):
                i += 2 if toks[i] in WRAPPER_VAL_FLAGS else 1
            continue
        if t in ("{", "(", "!"):
            i += 1; continue
        if t == "timeout":
            i += 2; continue
        if t in ("time", "nohup", "exec", "command", "setsid"):
            i += 1; continue
        break
    return toks[i:]

def non_flag_args(args, val_flags=()):
    pos, i = [], 0
    while i < len(args):
        a = args[i]
        if a == "--":
            pos.extend(args[i+1:]); break
        if a in val_flags:
            i += 2; continue
        if a.startswith("-"):
            i += 1; continue
        pos.append(a); i += 1
    return pos

def is_local_pip_only(args):
    i, saw_local = 0, False
    val_flags = {"--index-url", "-i", "--extra-index-url", "--find-links", "-f", "--target", "-t", "--prefix", "--root"}
    while i < len(args):
        a = args[i]
        if a in ("-e", "--editable") and i + 1 < len(args):
            target = args[i + 1]
            if re.match(r"^(\.|/|\.\.)", target) and "://" not in target and not target.startswith("git+"):
                saw_local = True; i += 2; continue
            return False
        if a in ("-r", "--requirement") and i + 1 < len(args):
            req = args[i + 1]
            if "://" not in req and not req.startswith("git+"):
                saw_local = True; i += 2; continue
            return False
        if a in val_flags:
            i += 2; continue
        if a.startswith("-"):
            i += 1; continue
        return False
    return saw_local

def extract_cmd_substs(text: str):
    subs = []
    sq = dq = esc = False
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if esc:
            esc = False; i += 1; continue
        if ch == "\\" and not sq:
            esc = True; i += 1; continue
        if ch == "\x27" and not dq:
            sq = not sq; i += 1; continue
        if ch == "\x22" and not sq:
            dq = not dq; i += 1; continue
        if not sq:
            if text[i:i+2] == "$(" or (ch in "<>" and not dq and text[i+1:i+2] == "("):
                depth_p = 1
                j = i + 2
                while j < n and depth_p > 0:
                    if text[j] == "(":
                        depth_p += 1
                    elif text[j] == ")":
                        depth_p -= 1
                    j += 1
                subs.append(text[i+2:j-1])
                i = j
                continue
            if ch == "`":
                j = i + 1
                while j < n and text[j] != "`":
                    if text[j] == "\\":
                        j += 2
                        continue
                    j += 1
                subs.append(text[i+1:j])
                i = j + 1
                continue
        i += 1
    return subs

def check_script(script: str, local_cwd: str, depth: int = 0):
    if depth > 4 or not script.strip():
        return None
    # Join line continuations and pipes split across lines; drop redirection-dup ampersands
    # (2>&1, &>, |&) so they are not mistaken for backgrounding.
    script = re.sub(r"\\\n", " ", script)
    script = re.sub(r"\|\s*\n", "| ", script)
    script = script.replace("&>", ">").replace(">&", ">").replace("|&", "|")
    cleaned = "\n".join(strip_comment(ln) for ln in strip_heredocs(script).splitlines())

    sub_ask = None
    for sub in extract_cmd_substs(cleaned):
        res = check_script(sub, local_cwd, depth + 1)
        if res and res[0] == "deny":
            return res
        if res and not sub_ask:
            sub_ask = res

    statements = split_top(cleaned, ";\n&|")
    if len(statements) == 1:
        lead = cleaned.lstrip()
        if re.match(r"^(git\s+commit|echo)\b", lead):
            return sub_ask

    if re.search(r"[({][^|\n]*\b(curl|wget)\b[^|\n]*[)}]\s*\|\s*(sudo\s+)?(sh|bash|zsh|dash|ksh|python3?|node|deno|perl|ruby|php)\b", cleaned):
        return ("deny", "install-guard: piping a grouped download into a shell/interpreter is blocked. Download to a file, inspect with repo-audit, then execute.")

    list_parts = []
    for line in cleaned.splitlines():
        for chunk, _ in split_top(line, ";&"):
            if chunk.strip():
                list_parts.append(chunk)

    ask_reason = sub_ask
    for pipeline in list_parts:
        stages = [s.strip() for s, _ in split_top(pipeline, "|") if s.strip()]
        saw_fetcher = False
        for idx, stage in enumerate(stages):
            try:
                raw_toks = shlex.split(stage, posix=True)
            except ValueError:
                raw_toks = stage.split()
            toks = unwrap_tokens(raw_toks)
            if not toks:
                continue
            prog = os.path.basename(toks[0].strip("(){}!"))
            rest = toks[1:]

            if prog in ("curl", "wget"):
                saw_fetcher = True
            elif saw_fetcher and idx > 0 and prog in ("sh", "bash", "zsh", "dash", "ksh", "python", "python3", "node", "deno", "perl", "ruby", "php"):
                fetcher = stages[0].split()[0]
                return ("deny", f"install-guard: piping {fetcher} output directly into {prog} is blocked. Download to a file, inspect with repo-audit, then execute.")

            if prog == "ssh":
                j = 0
                while j < len(rest):
                    if rest[j] in SSH_VAL_FLAGS:
                        j += 2
                    elif rest[j].startswith("-"):
                        j += 1
                    else:
                        j += 1
                        break
                if j < len(rest):
                    res = check_script(" ".join(rest[j:]), "", depth + 1)
                    if res and res[0] == "deny":
                        return res
                    if res and not ask_reason:
                        ask_reason = res
                continue

            if prog in ("bash", "sh", "zsh", "dash", "ksh", "eval", "source", "."):
                for sub in extract_cmd_substs(stage):
                    if FETCH_SUB_RE.match(sub):
                        return ("deny", f"install-guard: running a download via substitution inside `{prog}` is blocked. Download to a file, inspect with repo-audit, then execute.")
                for k, tk in enumerate(rest):
                    if tk.startswith("-") and "c" in tk[1:] and k + 1 < len(rest):
                        res = check_script(rest[k + 1], local_cwd, depth + 1)
                        if res and res[0] == "deny":
                            return res
                        if res and not ask_reason:
                            ask_reason = res
                        break
                continue

            hit = None
            if prog == "claude" and len(rest) >= 2 and rest[0] == "mcp" and rest[1] == "add":
                hit = " ".join(toks[:5])
            elif prog in ("pnpx", "bunx", "uvx"):
                pos = non_flag_args(rest, ("-p", "--package", "--from"))
                arg0 = pos[0] if pos else (rest[0] if rest else prog)
                hit = f"{prog} {arg0}"
            elif prog == "pipx" and rest and rest[0] in ("run", "install"):
                pos = non_flag_args(rest[1:])
                arg0 = pos[0] if pos else ""
                hit = f"pipx {rest[0]} {arg0}"
            elif prog == "npx":
                if any(a in ("-p", "--package") or a.startswith("--package=") for a in rest):
                    hit = " ".join(toks[:4])
                else:
                    pos = non_flag_args(rest)
                    if pos:
                        pkg = pos[0]
                        local_bin = os.path.join(local_cwd, "node_modules", ".bin", pkg) if local_cwd else ""
                        is_plain = ("/" not in pkg and "@" not in pkg)
                        if not (is_plain and local_bin and os.path.isfile(local_bin) and in_lockfile(pkg, local_cwd)):
                            hit = f"npx {pkg}"
            elif prog == "npm" and rest and rest[0] in ("exec", "x"):
                hit = " ".join(toks[:4])
            elif prog in ("pnpm", "yarn") and rest and rest[0] == "dlx":
                hit = " ".join(toks[:4])
            elif prog in ("python", "python3") and rest[:2] in (["-m", "pip"], ["-m", "uv"]) and "install" in rest[2:]:
                if not is_local_pip_only([a for a in rest[2:] if a != "install"]):
                    hit = " ".join(toks[:5])
            elif prog == "deno" and rest and rest[0] == "run" and any("://" in a for a in rest[1:]):
                hit = " ".join(toks[:4])
            elif prog == "npm" and rest and rest[0] in ("install", "i", "add", "isntall"):
                sub_args = rest[1:]
                pos = non_flag_args(sub_args, NPM_VAL_FLAGS)
                if any(a in ("-g", "--global") for a in sub_args) or pos:
                    hit = " ".join(["npm", rest[0], *(pos[:2] or ["-g"])])
            elif prog == "pnpm" and rest:
                if rest[0] == "add":
                    pos = non_flag_args(rest[1:], NPM_VAL_FLAGS)
                    arg0 = pos[0] if pos else ""
                    hit = f"pnpm add {arg0}"
                elif rest[0] in ("install", "i"):
                    sub_args = rest[1:]
                    pos = non_flag_args(sub_args, NPM_VAL_FLAGS)
                    if any(a in ("-g", "--global") for a in sub_args) or pos:
                        arg0 = pos[0] if pos else "-g"
                        hit = f"pnpm {rest[0]} {arg0}"
            elif prog == "yarn" and rest:
                if rest[0] == "add" or (rest[:2] == ["global", "add"]):
                    hit = " ".join(toks[:4])
            elif prog == "bun" and rest:
                if rest[0] in ("add", "x"):
                    hit = " ".join(toks[:4])
                elif rest[0] in ("install", "i"):
                    sub_args = rest[1:]
                    pos = non_flag_args(sub_args)
                    if any(a in ("-g", "--global") for a in sub_args) or pos:
                        hit = " ".join(toks[:4])
            elif prog in ("pip", "pip3") and rest and rest[0] == "install":
                if not is_local_pip_only(rest[1:]):
                    hit = " ".join(toks[:4])
            elif prog == "uv" and rest:
                if rest[0] == "add" or rest[:2] in (["tool", "install"], ["tool", "run"]):
                    hit = " ".join(toks[:4])
                elif rest[:2] == ["pip", "install"] and not is_local_pip_only(rest[2:]):
                    hit = " ".join(toks[:5])
            elif prog in ("cargo", "go", "brew", "gem") and rest and rest[0] == "install":
                hit = " ".join(toks[:4])

            if hit and not ask_reason:
                ask_reason = ("ask", f"install-guard: third-party package/MCP action `{hit.strip()}`. Run `repo-audit` first if unvetted, then approve.")

    return ask_reason

verdict = check_script(cmd, cwd)
if verdict:
    emit(verdict[0], verdict[1])
'
)
rc=$?
if [ "$rc" -ne 0 ]; then
  printf '%s\n' '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"ask","permissionDecisionReason":"install-guard: analysis failed; confirm the command manually."}}'
  exit 0
fi
[ -n "$out" ] && printf '%s\n' "$out"
exit 0
