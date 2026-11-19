"""Checks run over the scanned pages. Each returns findings: dicts with severity, code, text,
fix, count and file:line samples. Read-only."""
from __future__ import annotations

import re
from collections import Counter, defaultdict

from bs_rules import (BS5_ONLY, CLASS_MIGRATION, DATA_ATTRS, DECLARATIVE, JS_INIT,
                      STYLE_EXT, expand)

CLASS_ATTR_RX = re.compile(r"""\bclass(?:Name)?\s*=\s*["']([^"']*)["']""")
DATA_RX = re.compile(r"""\bdata-(%s)\s*=\s*["']([^"']*)["']""" % "|".join(DATA_ATTRS))
DIR_RX = re.compile(r"""<html[^>]*\bdir\s*=\s*["']([^"']+)["']""", re.I)
JS_TOOLTIP_RX = re.compile(r"""\.(tooltip|popover)\(|new\s+bootstrap\.(Tooltip|Popover)""")
HEX_STYLE_RX = re.compile(r"""style\s*=\s*["'][^"']*#[0-9a-fA-F]{3,8}""")


def F(sev, code, text, fix, samples=None, count=None):
    s = list(samples or [])
    return {"severity": sev, "code": code, "text": text, "fix": fix,
            "count": count if count is not None else len(s), "samples": s[:6]}


def compile_rules(rules):
    out = []
    for r in rules:
        old = r[0] if isinstance(r, tuple) else r
        out.append((r, re.compile(r"(?<![\w-])" + expand(old) + r"(?![\w-])")))
    return out


MIG = compile_rules(CLASS_MIGRATION)
BS5 = compile_rules(BS5_ONLY)


def class_hits(text: str, compiled):
    hits = defaultdict(list)
    for ln, line in enumerate(text.splitlines(), 1):
        if "class" not in line:
            continue
        for val in CLASS_ATTR_RX.findall(line):
            for rule, rx in compiled:
                if rx.search(val):
                    hits[rule].append(ln)
    return hits


def page_major(pg, default):
    m = pg.major
    return m if m and m != "mixed" else (m or default)


def versions(pages, project):
    """Repo-level version picture, plus the default major for pages with no own assets."""
    by_ver = defaultdict(set)
    for pg in pages:
        for a in pg.assets:
            if a.kind in ("bs-css", "theme") and a.version:
                by_ver[a.version].add(pg.layout or pg.path)
    majors = {v.split(".")[0] for v in by_ver}
    dep = project.installed_version("bootstrap")
    if not majors and dep:
        majors = {dep.split(".")[0]}
    default = majors.pop() if len(majors) == 1 else ""
    return by_ver, default


def check_versions(pages, project):
    out = []
    by_ver, default = versions(pages, project)
    majors = {v.split(".")[0] for v in by_ver}
    if len(majors) > 1:
        detail = "; ".join(f"{v}: {len(ls)} pages/layouts (e.g. {sorted(ls)[0]})"
                           for v, ls in sorted(by_ver.items()))
        out.append(F("high", "mixed-versions", f"Bootstrap majors {sorted(majors)} in one "
                     f"repo: {detail}", "pick one major per app; migrate the old layouts "
                     "(references/migration.md), then delete the old CSS/JS links"))
    allv = sorted(by_ver) or ([project.installed_version("bootstrap")]
                              if project.installed_version("bootstrap") else [])
    for v in allv:
        parts = v.split(".")
        if parts[0] == "5" and len(parts) > 1 and parts[1].isdigit() and int(parts[1]) < 3:
            out.append(F("medium", "old-minor", f"Bootstrap {v}: no color modes, *-subtle, "
                         "*-emphasis, focus-ring, text-bg-*", "upgrade to 5.3.9 before "
                         "theming (drop-in for 5.x, read the 5.3 notes for color modes)", [v]))
        if parts[0] == "6":
            out.append(F("info", "v6-alpha", f"Bootstrap {v} is alpha", "pin 5.3.9 for "
                         "client work until 6 reaches beta"))
    return out, default


def check_double_load(pages):
    out = []
    multi_css, multi_js, popper_dup, no_popper, mixed_rtl, mismatch = [], [], [], [], [], []
    for pg in pages:
        # alternatives in @if branches (head vs head_ar) are separate files with the same
        # major: only same-file duplicates or different majors are real double loads
        css = [a for a in pg.assets if a.kind in ("bs-css", "theme")
               and a.note != "Metronic plugins"]
        by_src = {}
        for a in css:
            by_src.setdefault(a.src, set()).add(a.ref)
        majors = {a.version.split(".")[0] for a in css if a.version}
        if any(len(v) > 1 for v in by_src.values()) or len(majors) > 1:
            multi_css.append(f"{pg.path}: " + ", ".join(sorted({a.ref.rsplit('/', 1)[-1]
                             for a in pg.assets if a.kind in ("bs-css", "theme")})))
        js = [a for a in pg.assets if a.kind == "bs-js"]
        js_src = {}
        for a in js:
            js_src.setdefault(a.src, set()).add(a.ref)
        if any(len(v) > 1 for v in js_src.values()) or \
                len({a.version.split(".")[0] for a in js if a.version}) > 1:
            multi_js.append(f"{pg.path}: " + ", ".join(sorted({a.ref for a in js})))
        if any(a.note == "bundle" for a in js) and any(a.kind == "popper" for a in pg.assets):
            popper_dup.append(pg.path)
        if js and not any(a.note in ("bundle", "bundled") for a in js) and \
                not any(a.kind == "popper" for a in pg.assets) and \
                re.search(r"""data-(bs-)?toggle=["'](dropdown|tooltip|popover)""", pg.text):
            no_popper.append(pg.path)
        cssv = {a.version.split(".")[0] for a in pg.assets
                if a.kind in ("bs-css", "theme") and a.version}
        jsv = {a.version.split(".")[0] for a in js if a.version}
        if cssv and jsv and cssv != jsv:
            mismatch.append(f"{pg.path}: CSS {sorted(cssv)} with JS {sorted(jsv)}")
        rtl_src = {}
        for a in pg.assets:
            if a.kind in ("bs-css", "theme"):
                rtl_src.setdefault(a.src, set()).add(a.rtl)
        if any(len(v) > 1 for v in rtl_src.values()):
            mixed_rtl.append(pg.path)
    if multi_css:
        out.append(F("high", "double-css", "more than one Bootstrap build on the same page "
                     "(CDN + admin theme, or two versions)", "keep one: the admin theme's "
                     "bundle already contains Bootstrap; remove the extra <link>",
                     multi_css, len(multi_css)))
    if multi_js:
        out.append(F("high", "double-js", "Bootstrap JS loaded twice on a page: events fire "
                     "twice, dropdowns open and close at once", "load one bootstrap(.bundle) "
                     "script per page", multi_js, len(multi_js)))
    if popper_dup:
        out.append(F("low", "popper-dup", "bootstrap.bundle already contains Popper, and "
                     "Popper is loaded again", "drop the separate popper script",
                     popper_dup, len(popper_dup)))
    if no_popper:
        out.append(F("medium", "popper-missing", "bootstrap.js without Popper on pages with "
                     "dropdowns/tooltips", "use bootstrap.bundle.min.js",
                     no_popper, len(no_popper)))
    if mismatch:
        out.append(F("high", "js-css-mismatch", "Bootstrap CSS and JS of different majors on "
                     "one page: BS5 JS reads data-bs-*, BS4 CSS styles BS4 markup, so half of "
                     "the components break", "load the JS that matches the CSS major",
                     mismatch, len(mismatch)))
    if mixed_rtl:
        out.append(F("high", "rtl-and-ltr", "both bootstrap.css and bootstrap.rtl.css on one "
                     "page", "load exactly one, chosen by dir", mixed_rtl, len(mixed_rtl)))
    return out


def check_markup(pages, default):
    out = []
    mig = defaultdict(list)
    bs5_on_4 = defaultdict(list)
    data_broken, data_tip = [], []
    for pg in pages:
        major = page_major(pg, default)
        if major == "5":
            for rule, lines in class_hits(pg.text, MIG).items():
                mig[rule] += [f"{pg.path}:{ln}" for ln in lines]
            has_js_init = bool(JS_TOOLTIP_RX.search(pg.text))
            for ln, line in enumerate(pg.text.splitlines(), 1):
                for attr, val in DATA_RX.findall(line):
                    if attr != "toggle":
                        continue
                    if val in DECLARATIVE:
                        data_broken.append(f"{pg.path}:{ln} data-toggle=\"{val}\"")
                    elif val in JS_INIT and not has_js_init:
                        data_tip.append(f"{pg.path}:{ln} data-toggle=\"{val}\"")
        elif major == "4":
            for rule, lines in class_hits(pg.text, BS5).items():
                bs5_on_4[rule] += [f"{pg.path}:{ln}" for ln in lines]
            for ln, line in enumerate(pg.text.splitlines(), 1):
                if "data-bs-" in line:
                    bs5_on_4["data-bs-*"].append(f"{pg.path}:{ln}")
    for (old, new, origin, note), hits in sorted(mig.items(), key=lambda kv: -len(kv[1])):
        sev = "high" if origin == "bs3" else "medium"
        out.append(F(sev, f"{origin}-class", f"{origin.upper()} class `{old}` on Bootstrap 5 "
                     f"pages has no style{': ' + note if note else ''}", f"replace with `{new}`",
                     hits, len(hits)))
    if data_broken:
        out.append(F("high", "data-toggle", "BS4 data-toggle on BS5 pages: these modals/"
                     "collapses/dropdowns/tabs do not open", "rename data-toggle/target/"
                     "dismiss/parent to data-bs-*", data_broken, len(data_broken)))
    if data_tip:
        out.append(F("low", "data-toggle-js", "tooltip/popover with BS4 data-toggle and no "
                     "JS init found", "use data-bs-toggle and init with "
                     "bootstrap.Tooltip.getOrCreateInstance", data_tip, len(data_tip)))
    for rule, hits in bs5_on_4.items():
        name = rule if isinstance(rule, str) else rule
        out.append(F("medium", "bs5-on-bs4", f"BS5 markup `{name}` on a Bootstrap 4 page "
                     "does nothing", "migrate the page to BS5, or use the BS4 class",
                     hits, len(hits)))
    return out


def check_rtl(pages):
    rtl_no_css, ltr_rtl_css, dynamic = [], [], 0
    for pg in pages:
        m = DIR_RX.search(pg.text)
        if not m:
            continue
        d = m.group(1).strip().lower()
        css = [a for a in pg.assets if a.kind in ("bs-css", "theme")]
        if not css:
            continue
        if "{{" in d or "<?" in d:
            dynamic += 1
            if not any(a.rtl for a in css):
                rtl_no_css.append(f"{pg.path}: dir is dynamic but only LTR CSS is loaded")
            continue
        if d == "rtl" and not any(a.rtl for a in css):
            rtl_no_css.append(pg.path)
        if d == "ltr" and any(a.rtl for a in css):
            ltr_rtl_css.append(pg.path)
    out = []
    if rtl_no_css:
        out.append(F("high", "rtl-css", "dir=rtl page loads LTR Bootstrap: spacing, dropdowns, "
                     "input groups and carets sit on the wrong side", "load bootstrap.rtl.min."
                     "css (or the theme's .rtl bundle) when dir=rtl", rtl_no_css,
                     len(rtl_no_css)))
    if ltr_rtl_css:
        out.append(F("medium", "ltr-rtl-css", "dir=ltr page loads the RTL build",
                     "pick the CSS file from the same variable as dir", ltr_rtl_css,
                     len(ltr_rtl_css)))
    return out


def check_tailwind(pages, project):
    out = []
    pages_both = [pg for pg in pages if any(a.kind == "tailwind" for a in pg.assets)
                  and any(a.kind in ("bs-css", "theme") for a in pg.assets)]
    cfg = next((project.root / n for n in ("tailwind.config.js", "tailwind.config.cjs",
                "tailwind.config.ts", "tailwind.config.mjs") if (project.root / n).exists()),
               None)
    cfg_txt = project.read(cfg) if cfg else ""
    if not pages_both and not (cfg and project.installed_version("bootstrap")):
        return out
    where = [pg.path for pg in pages_both] or ["repo has both bootstrap and tailwind deps"]
    cfg_off = bool(re.search(r"preflight\s*:\s*false", cfg_txt))
    notes = {a.note for pg in pages_both for a in pg.assets if a.kind == "tailwind"}
    # compiled CSS is the truth; a source file with preflight counts unless the config disables it
    preflight_on = "preflight" in notes or ("preflight-src" in notes and not cfg_off) or \
        (not notes - {""} and pages_both and not cfg_off)
    prefixed = bool(re.search(r"prefix\s*:\s*['\"]\w+", cfg_txt))
    cdn = any(a.kind == "tailwind" and "cdn.tailwindcss" in a.ref for pg in pages_both
              for a in pg.assets)
    if preflight_on or cdn:
        out.append(F("high", "tw-preflight", "Tailwind preflight resets headings, lists, "
                     "buttons, img and borders under Bootstrap (the play CDN always "
                     "includes it)", "v3: corePlugins.preflight=false; v4: import "
                     "tailwindcss/theme + tailwindcss/utilities without preflight; never the "
                     "play CDN in production", where, len(where)))
    if not prefixed:
        uses = [f"{pg.path}" for pg in pages_both if re.search(
            r"""class\s*=\s*["'][^"']*\bcollapse\b""", pg.text)]
        out.append(F("high" if uses else "medium", "tw-clash", "unprefixed Tailwind shares "
                     "class names with Bootstrap (collapse = visibility:collapse, container, "
                     "table, spacing scale, v4 col-*/w-*/h-*)", "set prefix tw (v3 prefix: "
                     "'tw-', v4 @import 'tailwindcss' prefix(tw)), or drop one framework",
                     uses or where, len(uses or where)))
    return out


def check_assets(pages):
    http, unpinned, no_sri = set(), set(), set()
    for pg in pages:
        for a in pg.assets:
            if a.ref.startswith("http://"):
                http.add(a.ref)
            if a.note == "unpinned" or "@latest" in a.ref:
                unpinned.add(a.ref)
            if a.kind in ("bs-css", "bs-js") and a.ref.startswith("https://") and \
                    "integrity" not in pg.text:
                no_sri.add(a.ref)
    out = []
    if http:
        out.append(F("medium", "http-asset", "assets loaded over http: blocked as mixed "
                     "content on https pages", "use https", sorted(http)))
    if unpinned:
        out.append(F("medium", "unpinned", "CDN URL without an exact version: the page can "
                     "change under you", "pin bootstrap@5.3.9", sorted(unpinned)))
    if no_sri:
        out.append(F("low", "no-sri", "CDN Bootstrap without integrity hash",
                     "add integrity + crossorigin (templates/cdn-tags.html)", sorted(no_sri)))
    return out


def check_custom_css(project, files, pages):
    imp, hexes = Counter(), []
    for f in files:
        # theme bundles and font kits are vendor code, not the app's own overrides
        if f.name.endswith(STYLE_EXT) and ".bundle." not in f.name and \
                "/fonts/" not in project.rel(f) and not re.match(
                    r"(style|plugins|vendors?|theme|core|app-assets)[.-]", f.name):
            imp[project.rel(f)] = project.read(f).count("!important")
    for pg in pages:
        n = len(HEX_STYLE_RX.findall(pg.text))
        if n:
            hexes.append((n, pg.path))
    out = []
    total = sum(imp.values())
    if total > 20:
        top = [f"{p}: {n}" for p, n in imp.most_common(5) if n]
        out.append(F("medium", "important-war", f"{total} !important in own CSS: overrides "
                     "fight Bootstrap's !important utilities", "move brand values into "
                     "--bs-* tokens (references/theming.md); keep !important only where a "
                     "theme rule forces it", top, total))
    if sum(n for n, _ in hexes) > 10:
        hexes.sort(reverse=True)
        out.append(F("low", "inline-hex", f"{sum(n for n, _ in hexes)} inline style colors in "
                     "templates", "replace with utility classes or tokens",
                     [f"{p}: {n}" for n, p in hexes[:6]], sum(n for n, _ in hexes)))
    return out


def check_frameworks(project, pages):
    out = []
    reqs = {**(project.composer.get("require") or {})}
    livewire = "livewire/livewire" in reqs
    alpine = bool(project.dep("alpinejs"))
    uses_js = [pg.path for pg in pages if re.search(
        r"""data-bs-toggle=["'](modal|tooltip|popover|dropdown|offcanvas)""", pg.text)]
    if (livewire or alpine) and uses_js:
        out.append(F("info", "rerender", f"{'Livewire' if livewire else 'Alpine'} re-renders "
                     "DOM that Bootstrap JS components hold", "wire:ignore.self on modals, "
                     "re-init tooltips after updates, dispose on hidden.bs.modal "
                     "(references/conflicts.md#re-render)", uses_js, len(uses_js)))
    jq = any(a.kind == "jquery" for pg in pages for a in pg.assets)
    bs5 = any(a.kind in ("bs-css", "theme") and a.version.startswith("5")
              for pg in pages for a in pg.assets)
    if jq and bs5:
        out.append(F("info", "jquery-bridge", "jQuery is loaded on BS5 pages: Bootstrap "
                     "registers jQuery plugins too", "fine for legacy $().modal(); add "
                     "data-bs-no-jquery on <body> once nothing calls them"))
    return out
