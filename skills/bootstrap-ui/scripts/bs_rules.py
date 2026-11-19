"""Rule data for bs_doctor. Every class pair was checked against the real dist CSS of
bootstrap 4.6.2 and 5.3.9 (old class present in the old CSS, absent in 5.3.9; replacement
present in 5.3.9) on 2026-11-19. Tailwind clashes come from real Tailwind 3.4.17 and 4.1.11
builds over the full 5.3.9 class list. references/migration.md is generated from this file.
"""
from __future__ import annotations

# (old class, BS5 replacement, origin, note). origin: bs4 or bs3.
CLASS_MIGRATION = [
    ("ml-{n}", "ms-{n}", "bs4", "margin-left is logical in BS5 (start), flips in RTL"),
    ("mr-{n}", "me-{n}", "bs4", "margin-right -> end"),
    ("pl-{n}", "ps-{n}", "bs4", "padding-left -> start"),
    ("pr-{n}", "pe-{n}", "bs4", "padding-right -> end"),
    ("float-left", "float-start", "bs4", ""),
    ("float-right", "float-end", "bs4", ""),
    ("text-left", "text-start", "bs4", ""),
    ("text-right", "text-end", "bs4", ""),
    ("border-left", "border-start", "bs4", ""),
    ("border-right", "border-end", "bs4", ""),
    ("rounded-left", "rounded-start", "bs4", ""),
    ("rounded-right", "rounded-end", "bs4", ""),
    ("dropdown-menu-right", "dropdown-menu-end", "bs4", ""),
    ("dropdown-menu-left", "dropdown-menu-start", "bs4", ""),
    ("badge-{color}", "text-bg-{color}", "bs4", "5.3 helper sets readable text color too"),
    ("badge-pill", "rounded-pill", "bs4", ""),
    ("custom-select", "form-select", "bs4", ""),
    ("custom-control", "form-check", "bs4", "with custom-checkbox / custom-radio"),
    ("custom-checkbox", "form-check", "bs4", "input gets form-check-input, label form-check-label"),
    ("custom-radio", "form-check", "bs4", ""),
    ("custom-switch", "form-check form-switch", "bs4", ""),
    ("custom-file", "form-control (type=file)", "bs4", ""),
    ("custom-range", "form-range", "bs4", ""),
    ("form-group", "mb-3", "bs4", "form-group is gone; use spacing utilities"),
    ("form-row", "row g-3", "bs4", ""),
    ("form-inline", "row row-cols-lg-auto g-3 align-items-center", "bs4", ""),
    ("input-group-append", "(remove: put the button/text inside .input-group)", "bs4", ""),
    ("input-group-prepend", "(remove: put the button/text inside .input-group)", "bs4", ""),
    ("btn-block", "w-100 (or d-grid wrapper)", "bs4", ""),
    ("close", "btn-close", "bs4", "btn-close is an empty button with aria-label"),
    ("sr-only", "visually-hidden", "bs4", ""),
    ("sr-only-focusable", "visually-hidden-focusable", "bs4", ""),
    ("no-gutters", "g-0", "bs4", ""),
    ("font-weight-{w}", "fw-{w}", "bs4", "bold, normal, light, bolder, lighter"),
    ("font-italic", "fst-italic", "bs4", ""),
    ("text-monospace", "font-monospace", "bs4", ""),
    ("media", "d-flex", "bs4", "media object removed; use flex utilities"),
    ("jumbotron", "p-5 mb-4 bg-body-tertiary rounded-3", "bs4", ""),
    ("card-deck", "row row-cols-1 row-cols-md-3 g-4", "bs4", ""),
    ("card-columns", "masonry layout (no BS5 class)", "bs4", ""),
    ("embed-responsive", "ratio ratio-16x9", "bs4", ""),
    ("pre-scrollable", "overflow-y-auto (with a max-height)", "bs4", ""),
    ("text-hide", "visually-hidden", "bs4", ""),
    ("thead-dark", "table-dark (on thead)", "bs4", ""),
    ("thead-light", "table-light (on thead)", "bs4", ""),
    ("btn-default", "btn-secondary or btn-outline-secondary", "bs3", ""),
    ("btn-xs", "btn-sm", "bs3", ""),
    ("col-xs-{col}", "col-{col}", "bs3", ""),
    ("hidden-xs", "d-none d-sm-block", "bs3", "and the other hidden-*/visible-* classes"),
    ("pull-right", "float-end", "bs3", ""),
    ("pull-left", "float-start", "bs3", ""),
    ("panel", "card", "bs3", "panel-heading -> card-header, panel-body -> card-body"),
    ("well", "card card-body bg-body-tertiary", "bs3", ""),
    ("glyphicon", "Bootstrap Icons (bi bi-*)", "bs3", ""),
    ("label-{color}", "badge text-bg-{color}", "bs3", ""),
    ("img-responsive", "img-fluid", "bs3", ""),
]

COLORS = "primary|secondary|success|danger|warning|info|light|dark"
PLACEHOLDERS = {"{n}": r"(?:[0-5]|auto|n[1-5])", "{color}": f"(?:{COLORS})",
                "{col}": r"(?:1[0-2]|[1-9])",
                "{w}": r"(?:bold|bolder|normal|light|lighter)"}

# BS5 classes that do not exist in BS4 (used to flag BS5 markup on a BS4 page).
BS5_ONLY = ["ms-{n}", "me-{n}", "ps-{n}", "pe-{n}", "float-start", "float-end", "text-start",
            "text-end", "form-select", "btn-close", "visually-hidden",
            "fw-bold", "g-0", "dropdown-menu-end", "text-bg-{color}"]

# data-* attributes BS5 renamed to data-bs-*. Declarative use of these is broken on BS5.
DATA_ATTRS = ["toggle", "target", "dismiss", "parent", "ride", "slide", "slide-to",
              "spy", "offset", "placement", "content", "trigger", "backdrop", "keyboard"]
# toggle values that need data-bs-toggle to work at all on BS5
DECLARATIVE = {"modal", "collapse", "dropdown", "tab", "pill", "offcanvas", "button", "list"}
# toggle values that work when the page initialises them by JS (jQuery bridge or new bootstrap.X)
JS_INIT = {"tooltip", "popover"}

# Tailwind classes that clash with Bootstrap and change behaviour, not only spacing values.
# Verified by building Tailwind 3.4.17 / 4.1.11 over the 5.3.9 class list.
TAILWIND_CLASHES = {
    "collapse": ("high", "Tailwind .collapse is visibility:collapse; an opened Bootstrap "
                         "collapse/navbar stays invisible"),
    "container": ("medium", "different max-widths and padding per breakpoint"),
    "table": ("medium", "Tailwind .table is display:table only; harmless alone, but "
                        "@layer order decides which wins"),
    "col-{n}": ("medium", "Tailwind v4 col-6 = grid-column:6 (adds to the Bootstrap grid "
                          "column; breaks inside CSS grid)"),
    "spacing": ("medium", "p-3/m-5/gap-3 mean 1rem/3rem/1rem in Bootstrap and "
                          "0.75rem/1.25rem/0.75rem in Tailwind; Bootstrap wins only because "
                          "its utilities are !important"),
    "w-h": ("low", "Tailwind v4 w-50/h-100 = 12.5rem/25rem, Bootstrap = 50%/100%"),
}

# Admin themes that ship their own Bootstrap build. (pattern, name, bootstrap major or None)
ADMIN_THEMES = [
    (r"style\.bundle(\.rtl)?(\.min)?\.css", "Metronic", None),
    (r"plugins\.bundle(\.rtl)?(\.min)?\.css", "Metronic plugins", None),
    (r"adminlte(\.rtl)?(\.min)?\.css", "AdminLTE", None),
    (r"@coreui/coreui|coreui(\.rtl)?(\.min)?\.css", "CoreUI", 5),
    (r"(^|/)vuexy[^/]*\.css", "Vuexy", None),
    (r"argon-dashboard|material-dashboard|light-bootstrap-dashboard", "Creative Tim", None),
]

EXCLUDE_DIRS = {"node_modules", "vendor", "bower_components", ".git", "storage", "dist",
                "build", ".next", ".nuxt", "coverage", "lib", "libs", "plugins",
                "bootstrap", ".venv", "__pycache__", "cache", "app-assets", "vendors",
                "assets-old", "backup", "backups"}
EXCLUDE_PATHS = ("public/vendor", "public/build", "public/assets/plugins",
                 "public/assets/vendors", "public/assets/js/scripts.bundle",
                 "resources/assets/vendors")
MARKUP_EXT = (".blade.php", ".html", ".htm", ".php", ".vue", ".jsx", ".tsx", ".twig",
              ".svelte", ".erb", ".cshtml")
STYLE_EXT = (".css", ".scss", ".sass")


def expand(pattern: str) -> str:
    """Turn a rule class like ml-{n} into a regex for a whole class token."""
    import re
    rx = re.escape(pattern)
    for ph, sub in PLACEHOLDERS.items():
        rx = rx.replace(re.escape(ph), sub)
    return rx
