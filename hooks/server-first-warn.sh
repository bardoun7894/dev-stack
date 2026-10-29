#!/bin/bash
# server-first-warn.sh — SessionStart hook (G21). On Darwin only, warn when cwd is inside a website repo.
# Never blocks; exits 0 always.
set -u
[ "$(uname -s 2>/dev/null)" = "Darwin" ] || exit 0

in=""
[ -t 0 ] || in=$(cat 2>/dev/null || true)

cwd=""
if [ -n "$in" ]; then
  cwd=$(printf '%s' "$in" | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
    c = d.get("cwd")
    if isinstance(c, str) and c.strip():
        print(c.strip())
except Exception:
    pass
' 2>/dev/null || true)
fi
[ -n "$cwd" ] || cwd="$PWD"
[ -d "$cwd" ] || exit 0

repo=$(git -C "$cwd" rev-parse --show-toplevel 2>/dev/null) || exit 0

# Not a website if mobile/desktop/Mac markers or .where-to-work local override exist
if [ -f "$repo/.where-to-work" ] && grep -qi 'local' "$repo/.where-to-work" 2>/dev/null; then exit 0; fi

python3 - "$repo" "$cwd" <<'PY' 2>/dev/null || true
import glob, json, os, sys

repo = sys.argv[1]
cwd = sys.argv[2]
web_deps = {"next", "vite", "nuxt", "astro", "react-dom", "express"}

def has_non_web_marker(d):
    if not os.path.isdir(d):
        return False
    if os.path.isfile(os.path.join(d, "pubspec.yaml")):
        return True
    if os.path.isfile(os.path.join(d, "Package.swift")):
        return True
    if glob.glob(os.path.join(d, "*.xcodeproj")):
        return True
    if os.path.isdir(os.path.join(d, "android")) and os.path.isdir(os.path.join(d, "ios")):
        return True
    return False

if has_non_web_marker(repo) or has_non_web_marker(cwd):
    sys.exit(0)

candidates = [repo]
for sub in ("frontend", "web", "client", "site", "app", "backend", "server", "api"):
    p = os.path.join(repo, sub)
    if os.path.isdir(p):
        candidates.append(p)
for group in ("apps", "packages"):
    gp = os.path.join(repo, group)
    if os.path.isdir(gp):
        try:
            for name in sorted(os.listdir(gp)):
                ep = os.path.join(gp, name)
                if os.path.isdir(ep):
                    candidates.append(ep)
        except Exception:
            pass

is_web = False
for d in candidates:
    if has_non_web_marker(d):
        continue
    pkg_path = os.path.join(d, "package.json")
    if os.path.isfile(pkg_path):
        try:
            with open(pkg_path, "r", encoding="utf-8") as f:
                pkg = json.load(f)
            if isinstance(pkg, dict):
                all_deps = set()
                for k in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
                    sec = pkg.get(k)
                    if isinstance(sec, dict):
                        all_deps.update(sec.keys())
                non_web_pkg = False
                for dep in all_deps:
                    dl = dep.lower()
                    if dl in ("electron", "tauri") or dl.startswith(("electron-", "@electron/", "@tauri-apps/")):
                        non_web_pkg = True
                        break
                if non_web_pkg:
                    if d == repo:
                        sys.exit(0)
                    continue
                if all_deps & web_deps:
                    is_web = True
                    break
        except Exception:
            pass

    comp_path = os.path.join(d, "composer.json")
    if os.path.isfile(comp_path):
        try:
            with open(comp_path, "r", encoding="utf-8") as f:
                comp = json.load(f)
            if isinstance(comp, dict):
                for k in ("require", "require-dev"):
                    sec = comp.get(k)
                    if isinstance(sec, dict) and "laravel/framework" in sec:
                        is_web = True
                        break
            if is_web:
                break
        except Exception:
            pass

if is_web:
    msg = (
        f"SERVER-FIRST: {repo} looks like a website; website work runs on ssh MyContabo "
        "(where-to-work skill). Mobile/desktop/Mac work stays local."
    )
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": msg,
        }
    }))
PY
exit 0
