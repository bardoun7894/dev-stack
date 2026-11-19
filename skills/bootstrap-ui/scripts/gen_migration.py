#!/usr/bin/env python3
"""Regenerate references/migration.md from bs_rules.py so the doctor and the doc never drift.

    python3 gen_migration.py          # writes ../references/migration.md
    python3 gen_migration.py --check  # exit 1 when the file is stale (used by the tests)
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bs_rules import BS5_ONLY, CLASS_MIGRATION, DATA_ATTRS, DECLARATIVE, JS_INIT  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "references" / "migration.md"


def render() -> str:
    L = ["# BS3 / BS4 to Bootstrap 5.3 migration", "",
         "Generated from `scripts/bs_rules.py` by `scripts/gen_migration.py`; edit the rules, "
         "not this file. Every pair was checked against the dist CSS of bootstrap 4.6.2 and "
         "5.3.9: the old class exists in the old CSS and not in 5.3.9, the new one exists in "
         "5.3.9. `{n}` = 0-5/auto (and n1-n5 for margins), `{color}` = theme color, `{w}` = "
         "bold/bolder/normal/light/lighter, `{col}` = 1-12.", "",
         "## Order of work", "",
         "1. One Bootstrap per layout: remove the old `<link>`/`<script>` (doctor codes "
         "`double-css`, `double-js`, `js-css-mismatch`).",
         "2. JS attributes: `data-toggle|target|dismiss|parent|ride|slide|spy` to `data-bs-*` "
         "(code `data-toggle`). Without this, modals, collapses, dropdowns and tabs do not open.",
         "3. Classes, table below (codes `bs4-class`, `bs3-class`). Do it with one sed per rule "
         "on a branch, then check the pages by eye in LTR and RTL.",
         "4. jQuery plugin calls (`$('#m').modal('show')`) keep working while jQuery is on "
         "`window`; move them to `bootstrap.Modal.getOrCreateInstance(el).show()` when you touch "
         "the file.", "",
         "## Class map", "", "| Old | Bootstrap 5.3 | From | Note |", "|---|---|---|---|"]
    for old, new, origin, note in CLASS_MIGRATION:
        L.append(f"| `{old}` | `{new}` | {origin.upper()} | {note} |")
    L += ["", "## data attributes", "",
          "Renamed to `data-bs-*`: " + ", ".join(f"`data-{a}`" for a in DATA_ATTRS) + ".", "",
          "Broken without the rename (declarative): " +
          ", ".join(f"`{v}`" for v in sorted(DECLARATIVE)) + ".",
          "Work only when initialised from JS: " + ", ".join(f"`{v}`" for v in sorted(JS_INIT)) +
          ".", "", "## BS5-only classes (wrong on a Bootstrap 4 page)", "",
          ", ".join(f"`{c}`" for c in BS5_ONLY) + ".", "",
          "## sed recipes (GNU sed on the server; review the diff before commit)", "", "```bash",
          "# data attributes, only inside .blade.php views",
          r"grep -rlE 'data-(toggle|target|dismiss|parent)=' resources/views | xargs sed -i -E "
          r"'s/\bdata-(toggle|target|dismiss|parent|ride|slide|slide-to|spy)=/data-bs-\1=/g'",
          "# margins/paddings left/right -> start/end",
          r"grep -rlE '\b(m|p)[lr]-([0-5]|auto)\b' resources/views | xargs sed -i -E "
          r"'s/\b([mp])l-([0-5]|auto)\b/\1s-\2/g; s/\b([mp])r-([0-5]|auto)\b/\1e-\2/g'",
          "# float/text/border/rounded left/right",
          r"sed -i -E 's/\b(float|text|border|rounded)-left\b/\1-start/g; "
          r"s/\b(float|text|border|rounded)-right\b/\1-end/g' FILES",
          "```", "",
          "The sed lines touch class text anywhere in the file, including words in copy or "
          "JS strings. Run the doctor again after, and read the diff.", ""]
    return "\n".join(L)


def main() -> int:
    text = render()
    if "--check" in sys.argv:
        return 0 if OUT.exists() and OUT.read_text() == text else 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text)
    print(OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
