"""Walk a project, find the CSS/JS each page loads, and resolve the Bootstrap version per page.

A page is a markup file. Its assets are its own <link>/<script>/@vite refs plus those of the
layout it extends (Blade @extends / <x-*-layout>) and the partials that layout @includes,
one level deep. Versions come from CDN URLs, local file headers, package.json, or the
admin theme bundle.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from bs_rules import ADMIN_THEMES, EXCLUDE_DIRS, EXCLUDE_PATHS, MARKUP_EXT, STYLE_EXT

TAG_RX = re.compile(r"<(?:link|script)\b[^>]*>", re.I)
REF_RX = re.compile(r"""(?:href|src)\s*=\s*(?:"([^"]+)"|'([^']+)')""", re.I)
VITE_RX = re.compile(r"""@vite\(\s*\[?([^)\]]*)""")
MIX_RX = re.compile(r"""(?:asset|mix|url|secure_asset)\(\s*['"]([^'"]+)['"]""")
EXTENDS_RX = re.compile(r"""@extends\(\s*['"]([^'"]+)['"]""")
INCLUDE_RX = re.compile(r"""@include(?:If|When|First)?\(\s*['"]([^'"]+)['"]""")
XLAYOUT_RX = re.compile(r"""<x-([\w.-]*layout[\w.-]*)""")
CDN_VER_RX = re.compile(r"bootstrap(?:@|/)(\d+)(?:\.(\d+))?(?:\.(\d+))?[^\s\"']*", re.I)
PREFLIGHT_RX = re.compile(r"box-sizing:\s*border-box;\s*(?:border(?:-width)?:\s*0|margin:\s*0)")
HEADER_VER_RX = re.compile(r"Bootstrap\s+(?:v|Reboot v|Grid v|Utilities v)?\s*(\d+)\.(\d+)\.(\d+)")


@dataclass
class Asset:
    ref: str
    kind: str            # bs-css, bs-js, popper, jquery, tailwind, theme, other
    version: str = ""    # "5.3.9", "4", "" unknown
    rtl: bool = False
    note: str = ""
    src: str = ""        # file the reference was found in
    via: str = "direct"  # direct (page/layout chain) or include (an @include partial)
    sri: bool = False    # the tag carries integrity=


@dataclass
class Page:
    path: str
    own: list = field(default_factory=list)
    layout: str = ""
    assets: list = field(default_factory=list)
    text: str = ""

    @property
    def bs_versions(self) -> set:
        v = {a.version.split(".")[0] for a in self.assets
             if a.kind in ("bs-css", "theme") and a.version}
        return v

    @property
    def major(self) -> str:
        v = self.bs_versions
        return v.pop() if len(v) == 1 else ("mixed" if v else "")


class Project:
    def __init__(self, root: str, extra_excludes: list | None = None):
        self.root = Path(root).resolve()
        self.extra = extra_excludes or []
        self.pkg = self._json("package.json")
        self.composer = self._json("composer.json")
        self.files: list[Path] = []
        self.view_roots: list[Path] = []
        self._header_cache: dict = {}

    def _json(self, name) -> dict:
        try:
            return json.loads((self.root / name).read_text())
        except (OSError, ValueError):
            return {}

    def dep(self, name: str) -> str:
        for sec in ("dependencies", "devDependencies"):
            v = (self.pkg.get(sec) or {}).get(name)
            if v:
                return v
        return ""

    def installed_version(self, name: str) -> str:
        try:
            return json.loads((self.root / "node_modules" / name / "package.json")
                              .read_text()).get("version", "")
        except (OSError, ValueError):
            return re.sub(r"^[^\d]*", "", self.dep(name))

    def excluded(self, rel: str) -> bool:
        parts = rel.split("/")
        if any(p in EXCLUDE_DIRS for p in parts[:-1]):
            return True
        if any(rel.startswith(x) or f"/{x}" in rel for x in EXCLUDE_PATHS):
            return True
        if ".min." in parts[-1] or parts[-1].endswith(".bundle.js"):
            return True
        return any(Path(rel).match(g) for g in self.extra)

    def walk(self):
        for dp, dns, fns in os.walk(self.root):
            dns[:] = [d for d in dns if d not in EXCLUDE_DIRS]
            if dp.replace(os.sep, "/").endswith("resources/views"):
                self.view_roots.append(Path(dp))
            for fn in fns:
                if fn.endswith(MARKUP_EXT + STYLE_EXT):
                    p = Path(dp) / fn
                    if not self.excluded(self.rel(p)):
                        self.files.append(p)
        return self.files

    def rel(self, p: Path) -> str:
        return str(p.relative_to(self.root)).replace(os.sep, "/")

    def read(self, p: Path, limit: int = 2_000_000) -> str:
        try:
            with open(p, encoding="utf-8", errors="replace") as fh:
                return fh.read(limit)
        except OSError:
            return ""

    # -- asset classification -------------------------------------------
    def local_file(self, ref: str) -> Path | None:
        ref = ref.split("?")[0].split("#")[0]
        m = MIX_RX.search(ref)
        if m:
            ref = m.group(1)
        if ref.startswith(("http:", "https:", "//", "data:")) or "{{" in ref:
            return None
        ref = ref.lstrip("./").lstrip("/")
        for base in (self.root / "public", self.root, self.root / "static", self.root / "www"):
            p = base / ref
            if p.is_file():
                return p
        return None

    def header_version(self, p: Path) -> str:
        if p not in self._header_cache:
            head = self.read(p, 400_000)
            m = HEADER_VER_RX.search(head)
            if m:
                v = ".".join(m.groups())
            elif "--bs-" in head:
                v = "5"
            elif re.search(r"\.ml-1\b|\.custom-select\b", head):
                v = "4"
            else:
                v = ""
            self._header_cache[p] = v
        return self._header_cache[p]

    def tailwind_preflight(self, ref: str) -> str:
        """'preflight', 'no-preflight' or '' (unknown) for a loaded Tailwind stylesheet."""
        if "cdn.tailwindcss" in ref:
            return "preflight"
        p = self.local_file(ref)
        if not p:
            return ""
        txt = self.read(p, 400_000)
        if PREFLIGHT_RX.search(txt):
            return "preflight"
        if re.search(r"""@tailwind\s+base|@import\s+['"]tailwindcss(/preflight)?['"]""", txt):
            return "preflight-src"
        return "no-preflight"

    def scss_uses_bootstrap(self, p: Path) -> bool:
        txt = self.read(p, 200_000)
        return bool(re.search(r"""@(?:import|use|forward)\s+['"]~?bootstrap""", txt))

    @staticmethod
    def normalise(ref: str) -> str:
        """{{ asset('x.css') }} -> x.css; drops query strings."""
        m = MIX_RX.search(ref)
        if m:
            ref = m.group(1)
        return ref.strip()

    def classify(self, ref: str) -> Asset:
        ref = self.normalise(ref)
        low = ref.lower()
        name = low.split("?")[0].rsplit("/", 1)[-1]
        rtl = ".rtl." in name or "rtl" in name.split(".")[0] or bool(
            re.search(r"(^|/)(css-rtl|rtl)/", low))
        if "tailwind" in low:
            return Asset(ref, "tailwind", note=self.tailwind_preflight(ref))
        if "popper" in low:
            return Asset(ref, "popper")
        if re.search(r"jquery(-\d[\d.]*)?(\.slim)?(\.min)?\.js", name):
            return Asset(ref, "jquery", note="slim" if "slim" in name else "")
        for rx, theme, major in ADMIN_THEMES:
            if re.search(rx, low):
                if name.endswith(".js"):
                    return Asset(ref, "other", note=theme)
                p = self.local_file(ref)
                v = self.header_version(p) if p else ""
                return Asset(ref, "theme", v or (str(major) if major else ""), rtl, theme)
        if re.fullmatch(r"bootstrap(\.rtl)?(\.min)?\.(css|scss)", name):
            m = CDN_VER_RX.search(low)
            v = ".".join(g for g in m.groups() if g) if m else ""
            p = None if v else self.local_file(ref)
            if p:
                v = self.header_version(p)
            return Asset(ref, "bs-css", v, rtl, "unpinned" if m and not m.group(3) else "")
        if re.fullmatch(r"bootstrap(\.bundle)?(\.esm)?(\.min)?\.js", name):
            m = CDN_VER_RX.search(low)
            v = ".".join(g for g in m.groups() if g) if m else ""
            p = None if v else self.local_file(ref)
            if p:
                v = self.header_version(p)
            return Asset(ref, "bs-js", v, note="bundle" if "bundle" in name else "")
        if name.endswith(".css"):
            p = self.local_file(ref)
            if p and re.search(r"tailwindcss v\d|--tw-[a-z]", self.read(p, 4096)):
                return Asset(ref, "tailwind", note=self.tailwind_preflight(ref))
        return Asset(ref, "other")

    def vite_assets(self, text: str) -> list:
        out = []
        for m in VITE_RX.finditer(text):
            for entry in re.findall(r"""['"]([^'"]+)['"]""", m.group(1)):
                p = self.root / entry
                if not p.is_file():
                    continue
                body = self.read(p, 200_000)
                if entry.endswith((".scss", ".sass")) and self.scss_uses_bootstrap(p):
                    out.append(Asset(entry, "bs-css", self.installed_version("bootstrap"),
                                     note="sass build"))
                if re.search(r"""@tailwind\s+base|@import\s+['"]tailwindcss['"/]""", body):
                    pre = bool(re.search(r"""@tailwind\s+base|@import\s+['"]tailwindcss"""
                                         r"""(/preflight)?['"]""", body))
                    out.append(Asset(entry, "tailwind",
                                     note="preflight-src" if pre else "no-preflight"))
                if entry.endswith((".js", ".ts")) and re.search(
                        r"""from\s+['"]bootstrap['"]|import\s+['"]bootstrap['"]|"""
                        r"""require\(\s*['"]bootstrap['"]""", body):
                    out.append(Asset(entry, "bs-js", self.installed_version("bootstrap"),
                                     note="bundled"))
        return out

    def own_assets(self, text: str, src: str = "") -> list:
        assets = []
        for tag in TAG_RX.findall(text):
            m = REF_RX.search(tag)
            if not m:
                continue
            r = self.normalise(m.group(1) or m.group(2))
            if re.search(r"\.(css|js|scss)(\?|#|$)|cdn\.tailwindcss|bootstrap@", r):
                a = self.classify(r)
                a.sri = "integrity" in tag.lower()
                assets.append(a)
        assets += self.vite_assets(text)
        for a in assets:
            a.src = src
        return assets

    def include_assets(self, text: str, near: Path) -> list:
        out = []
        for inc in INCLUDE_RX.findall(text):
            ip = self.view_path(inc, near)
            if ip:
                for a in self.own_assets(self.read(ip), self.rel(ip)):
                    a.via = "include"
                    out.append(a)
        return out

    # -- layouts ----------------------------------------------------------
    def view_path(self, dotted: str, near: Path | None = None) -> Path | None:
        """Resolve a Blade view name; in monorepos prefer the views root holding `near`."""
        roots = sorted(self.view_roots or [self.root / "resources" / "views"],
                       key=lambda r: 0 if near and str(near).startswith(str(r)) else 1)
        for base in roots:
            p = base / (dotted.replace(".", "/") + ".blade.php")
            if p.is_file():
                return p
        return None

    def layout_for(self, text: str, near: Path | None = None) -> Path | None:
        m = EXTENDS_RX.search(text)
        if m:
            return self.view_path(m.group(1), near)
        m = XLAYOUT_RX.search(text)
        if m:
            name = m.group(1)
            for cand in (f"layouts.{name.replace('-layout', '')}", f"components.{name}",
                         f"layouts.{name}"):
                p = self.view_path(cand, near)
                if p:
                    return p
        return None

    def layout_assets(self, p: Path, depth: int = 0) -> list:
        text = self.read(p)
        assets = self.own_assets(text, self.rel(p))
        if depth == 0:
            assets += self.include_assets(text, p)
            parent = self.layout_for(text, p)
            if parent and parent != p:
                assets += self.layout_assets(parent, 1)
        return assets

    def pages(self) -> list:
        out = []
        cache: dict = {}
        if not self.files:
            self.walk()
        for f in self.files:
            if not f.name.endswith(MARKUP_EXT):
                continue
            text = self.read(f)
            pg = Page(self.rel(f), text=text)
            pg.own = self.own_assets(text, pg.path)
            lay = self.layout_for(text, f)
            if lay:
                pg.layout = self.rel(lay)
                if lay not in cache:
                    cache[lay] = self.layout_assets(lay)
                pg.assets = pg.own + cache[lay]
            else:
                pg.assets = pg.own + self.include_assets(text, f)
            out.append(pg)
        return out
