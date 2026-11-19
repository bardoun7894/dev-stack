#!/usr/bin/env python3
"""contrast.py: WCAG 2.2 contrast check of a Bootstrap 5.3 theme, light and dark.

    python3 contrast.py THEME.css [BASE.css] [--json]

THEME is a compiled theme (theme.scss output) or bs-theme.css; pass the stock
bootstrap.min.css as BASE when THEME only overrides it. Resolves var(), rgb()/rgba(),
#hex and color-mix(in srgb, ...). Text pairs must reach 4.5:1. Exit 1 when one fails.
"""
from __future__ import annotations

import json
import re
import sys

BLOCK_RX = re.compile(r"([^{}]+)\{([^{}]*)\}")


def parse(css: str) -> list:
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    css = re.sub(r"@media[^{]*\{", "", css)          # flatten media blocks (prefers-color-scheme)
    out = []
    for sel, body in BLOCK_RX.findall(css):
        props = {}
        for decl in re.split(r";(?![^(]*\))", body):
            if ":" in decl:
                k, v = decl.split(":", 1)
                props[k.strip()] = v.strip()
        out.append((" ".join(sel.split()), props))
    return out


def merged(blocks, want) -> dict:
    d: dict = {}
    for sel, props in blocks:
        parts = [s.strip().replace('"', "").replace("'", "") for s in sel.split(",")]
        if any(p in want for p in parts):
            d.update(props)
    return d


def resolve(val: str, env: dict, depth=0) -> str:
    if depth > 12:
        return val
    def sub(m):
        name, fb = m.group(1), m.group(2)
        v = env.get(name)
        return resolve(v, env, depth + 1) if v is not None else (fb or "")
    return re.sub(r"var\(\s*(--[\w-]+)\s*(?:,\s*([^()]*))?\)", sub, val)


def color(val: str, env: dict):
    """-> (r, g, b, a) floats 0..1, or None."""
    v = resolve(val, env).strip().lower()
    if v.startswith("#"):
        h = v[1:]
        if len(h) in (3, 4):
            h = "".join(c * 2 for c in h)
        a = int(h[6:8], 16) / 255 if len(h) == 8 else 1.0
        return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)) + (a,)
    m = re.match(r"rgba?\(([^)]*)\)", v)
    if m:
        nums = [x for x in re.split(r"[\s,/]+", m.group(1)) if x]
        r, g, b = (float(x) / 255 for x in nums[:3])
        a = float(nums[3].rstrip("%")) / (100 if nums[3].endswith("%") else 1) if len(nums) > 3 else 1
        return (r, g, b, a)
    m = re.match(r"color-mix\(in srgb,\s*(.+?)\s+([\d.]+)%\s*,\s*(.+)\)$", v)
    if m:
        c1, p, c2 = color(m.group(1), env), float(m.group(2)) / 100, color(m.group(3), env)
        if c1 and c2:
            return tuple(c1[i] * p + c2[i] * (1 - p) for i in range(3)) + (1.0,)
    named = {"white": (1, 1, 1, 1), "black": (0, 0, 0, 1), "#fff": (1, 1, 1, 1)}
    return named.get(v)


def over(fg, bg):
    a = fg[3]
    return tuple(fg[i] * a + bg[i] * (1 - a) for i in range(3)) + (1.0,)


def lum(c):
    def ch(x):
        return x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4
    r, g, b = (ch(x) for x in c[:3])
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def ratio(fg, bg) -> float:
    """Unrounded; round only for display, so 4.496 never passes as 4.5."""
    fg = over(fg, bg)
    l1, l2 = sorted((lum(fg), lum(bg)), reverse=True)
    return (l1 + 0.05) / (l2 + 0.05)


def check(blocks) -> list:
    light_sel = {":root", "[data-bs-theme=light]"}
    dark_sel = {"[data-bs-theme=dark]"}
    rows = []
    for mode in ("light", "dark"):
        env = merged(blocks, light_sel)
        if mode == "dark":
            env = {**env, **merged(blocks, dark_sel)}
        bg = color("var(--bs-body-bg)", env)
        card_env = {**env, **merged(blocks, {".card"})}
        if mode == "dark":
            card_env.update(merged(blocks, {"[data-bs-theme=dark] .card"}))
        card = color("var(--bs-card-bg, var(--bs-body-bg))", card_env) or bg
        if not bg:
            rows.append({"mode": mode, "pair": "body background (unparsed color)", "ratio": 0,
                         "need": 4.5, "ok": False})
            continue
        pairs = [
            ("body text on page", "var(--bs-body-color)", bg, 4.5),
            ("body text on card", "var(--bs-body-color)", card, 4.5),
            ("secondary text on page", "var(--bs-secondary-color)", bg, 4.5),
            ("secondary text on card", "var(--bs-secondary-color)", card, 4.5),
            ("link on card", "var(--bs-link-color)", card, 4.5),
            ("primary emphasis on primary subtle", "var(--bs-primary-text-emphasis)",
             color("var(--bs-primary-bg-subtle)", env), 4.5),
            ("border vs card (non-text, info)", "var(--bs-border-color)", card, 1.0),
        ]
        for name in ("success", "danger", "warning", "info"):
            pairs.append((f"{name} emphasis on {name} subtle",
                          f"var(--bs-{name}-text-emphasis)",
                          color(f"var(--bs-{name}-bg-subtle)", env), 4.5))
        for label, fg, b, need in pairs:
            f = color(fg, env)
            if not resolve(fg, env).strip() or "unset" in label:
                continue
            if f and b:
                r = ratio(f, b)
                rows.append({"mode": mode, "pair": label, "ratio": r, "need": need,
                             "ok": r >= need})
            else:   # a color we cannot parse (hsl, oklch, named) must not pass silently
                rows.append({"mode": mode, "pair": label + " (unparsed color)", "ratio": 0,
                             "need": need, "ok": False})
        for sel, props in blocks:
            m = re.fullmatch(r"(\[data-bs-theme=\"?dark\"?\] )?\.btn-(primary|secondary|success|"
                             r"danger|warning|info)", sel.replace("'", '"'))
            if not m or bool(m.group(1)) != (mode == "dark"):
                continue
            benv = {**env, **merged(blocks, {f".btn-{m.group(2)}"})}
            if mode == "dark":
                benv.update(props)
            for state in ("", "hover-"):
                f = color(f"var(--bs-btn-{state}color)", benv)
                b = color(f"var(--bs-btn-{state}bg)", benv)
                if f and b:
                    r = ratio(f, b)
                    rows.append({"mode": mode, "pair": f"btn-{m.group(2)} {state or 'rest'}",
                                 "ratio": r, "need": 4.5, "ok": r >= 4.5})
        if mode == "light":
            for sel, props in blocks:
                m = re.fullmatch(r"\.btn-(primary|secondary|success|danger|warning|info)", sel)
                if m and "--bs-btn-bg" in props:
                    benv = {**env, **props}
                    f = color("var(--bs-btn-color)", benv)
                    b = color("var(--bs-btn-bg)", benv)
                    if f and b:
                        r = ratio(f, b)
                        rows.append({"mode": "light", "pair": f"btn-{m.group(1)} rest",
                                     "ratio": r, "need": 4.5, "ok": r >= 4.5})
    seen, out = set(), []
    for r in rows:
        k = (r["mode"], r["pair"])
        if k not in seen:
            seen.add(k)
            out.append(r)
    return out


def main(argv=None) -> int:
    args = [a for a in (argv or sys.argv[1:]) if not a.startswith("--")]
    if not args:
        print(__doc__)
        return 2
    css = "".join(open(p, encoding="utf-8").read() for p in reversed(args))
    rows = check(parse(css))
    if "--json" in (argv or sys.argv[1:]):
        print(json.dumps(rows, indent=2))
    else:
        for r in rows:
            mark = "ok  " if r["ok"] else "FAIL"
            print(f"{mark} {r['mode']:5} {r['ratio']:5.2f} (need {r['need']}) {r['pair']}")
    if not rows:
        print("FAIL no color tokens found: is this a Bootstrap 5.3 theme?")
        return 1
    return 0 if all(r["ok"] for r in rows) else 1


if __name__ == "__main__":
    sys.exit(main())
