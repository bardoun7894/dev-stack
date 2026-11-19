# BS3 / BS4 to Bootstrap 5.3 migration

Generated from `scripts/bs_rules.py` by `scripts/gen_migration.py`; edit the rules, not this file. Every pair was checked against the dist CSS of bootstrap 4.6.2 and 5.3.9: the old class exists in the old CSS and not in 5.3.9, the new one exists in 5.3.9. `{n}` = 0-5/auto (and n1-n5 for margins), `{color}` = theme color, `{w}` = bold/bolder/normal/light/lighter.

## Order of work

1. One Bootstrap per layout: remove the old `<link>`/`<script>` (doctor codes `double-css`, `double-js`, `js-css-mismatch`).
2. JS attributes: `data-toggle|target|dismiss|parent|ride|slide|spy` to `data-bs-*` (code `data-toggle`). Without this, modals, collapses, dropdowns and tabs do not open.
3. Classes, table below (codes `bs4-class`, `bs3-class`). Do it with one sed per rule on a branch, then check the pages by eye in LTR and RTL.
4. jQuery plugin calls (`$('#m').modal('show')`) keep working while jQuery is on `window`; move them to `bootstrap.Modal.getOrCreateInstance(el).show()` when you touch the file.

## Class map

| Old | Bootstrap 5.3 | From | Note |
|---|---|---|---|
| `ml-{n}` | `ms-{n}` | BS4 | margin-left is logical in BS5 (start), flips in RTL |
| `mr-{n}` | `me-{n}` | BS4 | margin-right -> end |
| `pl-{n}` | `ps-{n}` | BS4 | padding-left -> start |
| `pr-{n}` | `pe-{n}` | BS4 | padding-right -> end |
| `float-left` | `float-start` | BS4 |  |
| `float-right` | `float-end` | BS4 |  |
| `text-left` | `text-start` | BS4 |  |
| `text-right` | `text-end` | BS4 |  |
| `border-left` | `border-start` | BS4 |  |
| `border-right` | `border-end` | BS4 |  |
| `rounded-left` | `rounded-start` | BS4 |  |
| `rounded-right` | `rounded-end` | BS4 |  |
| `dropdown-menu-right` | `dropdown-menu-end` | BS4 |  |
| `dropdown-menu-left` | `dropdown-menu-start` | BS4 |  |
| `badge-{color}` | `text-bg-{color}` | BS4 | 5.3 helper sets readable text color too |
| `badge-pill` | `rounded-pill` | BS4 |  |
| `custom-select` | `form-select` | BS4 |  |
| `custom-control` | `form-check` | BS4 | with custom-checkbox / custom-radio |
| `custom-checkbox` | `form-check` | BS4 | input gets form-check-input, label form-check-label |
| `custom-radio` | `form-check` | BS4 |  |
| `custom-switch` | `form-check form-switch` | BS4 |  |
| `custom-file` | `form-control (type=file)` | BS4 |  |
| `custom-range` | `form-range` | BS4 |  |
| `form-group` | `mb-3` | BS4 | form-group is gone; use spacing utilities |
| `form-row` | `row g-3` | BS4 |  |
| `form-inline` | `row row-cols-lg-auto g-3 align-items-center` | BS4 |  |
| `input-group-append` | `(remove: put the button/text inside .input-group)` | BS4 |  |
| `input-group-prepend` | `(remove: put the button/text inside .input-group)` | BS4 |  |
| `btn-block` | `w-100 (or d-grid wrapper)` | BS4 |  |
| `close` | `btn-close` | BS4 | btn-close is an empty button with aria-label |
| `sr-only` | `visually-hidden` | BS4 |  |
| `sr-only-focusable` | `visually-hidden-focusable` | BS4 |  |
| `no-gutters` | `g-0` | BS4 |  |
| `font-weight-{w}` | `fw-{w}` | BS4 | bold, normal, light, bolder, lighter |
| `font-italic` | `fst-italic` | BS4 |  |
| `text-monospace` | `font-monospace` | BS4 |  |
| `media` | `d-flex` | BS4 | media object removed; use flex utilities |
| `jumbotron` | `p-5 mb-4 bg-body-tertiary rounded-3` | BS4 |  |
| `card-deck` | `row row-cols-1 row-cols-md-3 g-4` | BS4 |  |
| `card-columns` | `masonry layout (no BS5 class)` | BS4 |  |
| `embed-responsive` | `ratio ratio-16x9` | BS4 |  |
| `pre-scrollable` | `overflow-y-auto (with a max-height)` | BS4 |  |
| `text-hide` | `visually-hidden` | BS4 |  |
| `thead-dark` | `table-dark (on thead)` | BS4 |  |
| `thead-light` | `table-light (on thead)` | BS4 |  |
| `btn-default` | `btn-secondary or btn-outline-secondary` | BS3 |  |
| `btn-xs` | `btn-sm` | BS3 |  |
| `col-xs-{n}` | `col-{n}` | BS3 |  |
| `hidden-xs` | `d-none d-sm-block` | BS3 | and the other hidden-*/visible-* classes |
| `pull-right` | `float-end` | BS3 |  |
| `pull-left` | `float-start` | BS3 |  |
| `panel` | `card` | BS3 | panel-heading -> card-header, panel-body -> card-body |
| `well` | `card card-body bg-body-tertiary` | BS3 |  |
| `glyphicon` | `Bootstrap Icons (bi bi-*)` | BS3 |  |
| `label-{color}` | `badge text-bg-{color}` | BS3 |  |
| `img-responsive` | `img-fluid` | BS3 |  |

## data attributes

Renamed to `data-bs-*`: `data-toggle`, `data-target`, `data-dismiss`, `data-parent`, `data-ride`, `data-slide`, `data-slide-to`, `data-spy`, `data-offset`, `data-placement`, `data-content`, `data-trigger`, `data-backdrop`, `data-keyboard`.

Broken without the rename (declarative): `button`, `collapse`, `dropdown`, `list`, `modal`, `offcanvas`, `pill`, `tab`.
Work only when initialised from JS: `popover`, `tooltip`.

## BS5-only classes (wrong on a Bootstrap 4 page)

`ms-{n}`, `me-{n}`, `ps-{n}`, `pe-{n}`, `float-start`, `float-end`, `text-start`, `text-end`, `form-select`, `btn-close`, `visually-hidden`, `fw-bold`, `g-0`, `dropdown-menu-end`, `text-bg-{color}`.

## sed recipes (GNU sed on the server; review the diff before commit)

```bash
# data attributes, only inside .blade.php views
grep -rlE 'data-(toggle|target|dismiss|parent)=' resources/views | xargs sed -i -E 's/\bdata-(toggle|target|dismiss|parent|ride|slide|slide-to|spy)=/data-bs-\1=/g'
# margins/paddings left/right -> start/end
grep -rlE '\b(m|p)[lr]-([0-5]|auto)\b' resources/views | xargs sed -i -E 's/\b([mp])l-([0-5]|auto)\b/\1s-\2/g; s/\b([mp])r-([0-5]|auto)\b/\1e-\2/g'
# float/text/border/rounded left/right
sed -i -E 's/\b(float|text|border|rounded)-left\b/\1-start/g; s/\b(float|text|border|rounded)-right\b/\1-end/g' FILES
```

The sed lines touch class text anywhere in the file, including words in copy or JS strings. Run the doctor again after, and read the diff.
