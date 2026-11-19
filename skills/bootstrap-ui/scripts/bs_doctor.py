#!/usr/bin/env python3
"""bs_doctor: read-only Bootstrap conflict and health scan of a project.

    python3 bs_doctor.py PATH [--json] [--out DIR] [--exclude GLOB ...] [--only CODE ...]

Finds: mixed Bootstrap versions per layout, double CSS/JS, BS3/BS4 markup on BS5 pages and
the reverse, BS4 data-toggle, RTL without the RTL build, Tailwind preflight and class
clashes, http/unpinned CDN assets, !important wars, Livewire/Alpine re-render risks.
Exit 0 = no high findings, 1 = high findings, 2 = bad usage.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bs_checks import (check_assets, check_custom_css, check_double_load,  # noqa: E402
                       check_frameworks, check_markup, check_rtl, check_tailwind,
                       check_versions)
from bs_scan import Project  # noqa: E402

ORDER = {"high": 0, "medium": 1, "low": 2, "info": 3}


def run(root: str, excludes=None, only=None) -> dict:
    project = Project(root, excludes)
    files = project.walk()
    pages = project.pages()
    findings, default = check_versions(pages, project)
    findings += check_double_load(pages)
    findings += check_markup(pages, default)
    findings += check_rtl(pages)
    findings += check_tailwind(pages, project)
    findings += check_assets(pages)
    findings += check_custom_css(project, files, pages)
    findings += check_frameworks(project, pages)
    if only:
        findings = [f for f in findings if f["code"] in only]
    findings.sort(key=lambda f: (ORDER[f["severity"]], -f["count"]))
    layouts: dict = {}
    for pg in pages:
        key = pg.layout or (pg.path if pg.own else "")
        if key and key not in layouts:
            layouts[key] = sorted({f"{a.kind}:{a.version or '?'}{':rtl' if a.rtl else ''}"
                                   f"{':' + a.note if a.note else ''}"
                                   for a in pg.assets if a.kind != "other"})
    return {"root": str(project.root), "pages": len(pages),
            "files": len(files), "default_major": default,
            "bootstrap_dep": project.dep("bootstrap"),
            "tailwind_dep": project.dep("tailwindcss"),
            "layouts": layouts, "findings": findings}


def markdown(rep: dict) -> str:
    L = [f"# Bootstrap doctor: {rep['root']}", "",
         f"- Scanned {rep['files']} files, {rep['pages']} markup pages. "
         f"Default Bootstrap major: {rep['default_major'] or 'unknown'}. "
         f"package.json bootstrap: {rep['bootstrap_dep'] or '-'}, "
         f"tailwindcss: {rep['tailwind_dep'] or '-'}.", "", "## Findings", ""]
    if not rep["findings"]:
        L.append("No findings.")
    for i, f in enumerate(rep["findings"], 1):
        n = f" ({f['count']})" if f["count"] else ""
        L.append(f"- F{i} [{f['severity']}] `{f['code']}` {f['text']}{n}. Fix: {f['fix']}")
        for s in f["samples"]:
            L.append(f"  - {s}")
    L += ["", "## What each layout loads", ""]
    for lay, assets in sorted(rep["layouts"].items())[:40]:
        L.append(f"- `{lay}`: {', '.join(assets) or 'nothing detected'}")
    if len(rep["layouts"]) > 40:
        L.append(f"- ... {len(rep['layouts']) - 40} more (see --json)")
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("path")
    p.add_argument("--json", action="store_true")
    p.add_argument("--out", help="directory for doctor.md + doctor.json")
    p.add_argument("--exclude", action="append", default=[], help="extra glob to skip")
    p.add_argument("--only", action="append", help="keep only these finding codes")
    a = p.parse_args(argv)
    if not Path(a.path).is_dir():
        print(f"not a directory: {a.path}", file=sys.stderr)
        return 2
    rep = run(a.path, a.exclude, a.only)
    md = markdown(rep)
    if a.out:
        d = Path(a.out)
        d.mkdir(parents=True, exist_ok=True)
        (d / "doctor.json").write_text(json.dumps(rep, indent=2, ensure_ascii=False))
        (d / "doctor.md").write_text(md)
        print(f"wrote {d / 'doctor.md'}", file=sys.stderr)
    print(json.dumps(rep, indent=2, ensure_ascii=False) if a.json else md, end="")
    return 1 if any(f["severity"] == "high" for f in rep["findings"]) else 0


if __name__ == "__main__":
    sys.exit(main())
