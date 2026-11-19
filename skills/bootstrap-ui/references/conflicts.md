# Bootstrap conflicts: causes and fixes

One section per `bs_doctor.py` finding code. "Verified" means checked against the bootstrap 5.3.9
dist or real Tailwind 3.4.17 / 4.1.11 builds on 2026-11-19; "docs" cites getbootstrap.com 5.3.

## mixed-versions, double-css, js-css-mismatch

Cause: a layout loads a CDN Bootstrap and the admin theme's bundle, which already contains its own
Bootstrap. Or the CSS is 4.x and the JS is 5.x. Seen in the owner's apps:
- beldify admin: BS 4.2.1 theme CSS (`app-assets`) with BS 5.3.2 JS;
- abd: BS 4.3.1 CDN on some views, Metronic's BS5 on others;
- hany-pos: BS 5.1.3 next to UltimatePOS BS3.

Fix:
1. Decide the one Bootstrap per layout. Admin themes win: Metronic 8 and CoreUI 5 are BS5, AdminLTE 3 is BS4, and Pixinvent "app-assets" themes are BS4.
2. Delete the extra `<link>`/`<script>`. Never keep two "just in case".
3. JS must match the CSS major. BS5 JS reads only `data-bs-*`. BS4 JS needs jQuery and reads `data-*`.
4. Pages written for the other major: migrate them (`migration.md`) or move them under a layout of their own major. Do not load both.

## data-toggle (BS4 attributes on BS5)

`data-toggle="modal|collapse|dropdown|tab|pill|offcanvas"` does nothing on BS5. Rename to `data-bs-*`; the sed recipe is in `migration.md`. Tooltips and popovers still work when the page calls `$(..).tooltip()`, because jQuery is on `window` and BS5 registers jQuery plugins (docs: getting-started/javascript).

## bs4-class, bs3-class, bs5-on-bs4

The class has no CSS in the loaded major, so the element is unstyled. `migration.md` maps every class.

The biggest visual breaks after a BS4 to BS5 swap:
- `form-group` loses its spacing;
- `input-group-prepend`/`-append` stop gluing;
- `ml-*`/`mr-*` stop flipping in RTL;
- `badge-*` loses its color;
- `close` loses its ×.

## rtl-css, ltr-rtl-css, rtl-and-ltr

`dir="rtl"` needs `bootstrap.rtl.min.css`, or the theme's `.rtl` bundle such as Metronic `style.bundle.rtl.css`. BS5 RTL is produced by RTLCSS, and logical classes (`ms-*`, `me-*`, `text-start`, `float-end`) do the flipping. Physical classes (`ml-*`, `text-left`) never flip.

Choose the file and `dir` from the same variable (template in `templates/cdn-tags.html`). Loading both files on one page makes the last one win for every rule.

The doctor counts head partials included under `@if` as alternatives, not as double loads.

## tw-preflight, tw-clash (Bootstrap + Tailwind on one page)

Verified on real builds of the full 5.3.9 class list: 186 class names collide with Tailwind 3 and 209 with Tailwind 4. The ones that change behaviour:

| Class | Bootstrap | Tailwind | Effect |
|---|---|---|---|
| `collapse` | `.collapse:not(.show){display:none}` | `visibility: collapse` | An opened navbar or accordion stays invisible |
| `container` | Gutters, max-width per breakpoint | `width:100%` plus breakpoint max-widths (v3) | Width jumps |
| `table` | Full table component | `display: table` | Order decides; usually harmless |
| `p-3`, `m-5`, `gap-3` | 1rem / 3rem / 1rem `!important` | 0.75rem / 1.25rem / 0.75rem | Bootstrap wins only through `!important` |
| `col-6` (v4) | `flex: 0 0 auto; width: 50%` | `grid-column: 6` | Breaks inside CSS grid |
| `w-50`, `h-100` (v4) | 50% / 100% | 12.5rem / 25rem | Bootstrap wins only through `!important` |

Preflight (Tailwind's reset) removes heading sizes, list bullets, button styles and borders under Bootstrap components. The doctor reads the compiled Tailwind CSS. A rule like `*,:after,:before{box-sizing:border-box;border:0 solid ...}` means preflight is on. This is the case in beldify admin.

Fix, in order of preference:
1. One framework per layout. Bootstrap admin pages and Tailwind public pages use separate layouts and separate CSS bundles.
2. If both must coexist:
   - v3: `prefix: 'tw-'` and `corePlugins: { preflight: false }` in `tailwind.config.js`, then rebuild.
   - v4: `@import "tailwindcss/theme.css" layer(theme) prefix(tw); @import "tailwindcss/utilities.css" layer(utilities) prefix(tw);` with no preflight import.

   Either way, never load the play CDN (`cdn.tailwindcss.com`), because it always ships preflight.

   Verified with 4.1.11: that v4 import emits no preflight and no `.collapse`/`.p-3`, and classes are written `tw:flex`, `tw:p-3` (colon, variant style). v3 classes are written `tw-flex`.
3. After the change, search the views for unprefixed Tailwind classes. With a prefix they silently stop working.

## important-war

Cause: hundreds of `!important` rules to beat Bootstrap. Bootstrap utilities are `!important` by default (`$enable-important-utilities: true`), and theme bundles add more.

Fix (KB [[abd/bootstrap-brand-recolor]]):
1. Count the selectors first. In abd, `btn-primary` ×354, `text-hover-primary` ×109 and `text-primary` ×98 made up 90% of the brand surface.
2. Override those few selectors through tokens (`--bs-*` or the theme's own variables) in one `app-ui.css` loaded last.
3. Keep semantic colors semantic.
4. Add `!important` only where a measured theme rule forces it, and write down why.
5. Watch the RGB triplet trap: `--bs-primary-rgb` must be `r, g, b` of the same color, or tints show the old blue.

## popper-dup, popper-missing, double-js

`bootstrap.bundle.min.js` already includes Popper, so do not add `popper.min.js` next to it. Plain `bootstrap.min.js` needs Popper loaded first for dropdowns, tooltips and popovers. Load exactly one Bootstrap JS per page: two copies bind every `data-bs-*` twice, so a dropdown opens and closes on the same click.

## re-render (Livewire, Alpine, Vue)

Bootstrap JS keeps instances on DOM nodes; a framework that replaces those nodes leaves stale instances, stuck backdrops and dead tooltips. Docs facts: `getOrCreateInstance(el)`, `getInstance(el)` returns null when none exists, `dispose()` after the `hidden.bs.*` event because methods are async.

Livewire 3 recipe:

```html
<div class="modal fade" id="orderModal" tabindex="-1" wire:ignore.self> ... </div>
<script>
  // open/close from PHP: $this->dispatch('modal', id: 'orderModal', action: 'show')
  window.addEventListener('modal', e => {
    const m = bootstrap.Modal.getOrCreateInstance(document.getElementById(e.detail.id));
    e.detail.action === 'hide' ? m.hide() : m.show();
  });
  // tooltips inside re-rendered markup
  const initTips = (root = document) => root.querySelectorAll('[data-bs-toggle="tooltip"]')
    .forEach(el => bootstrap.Tooltip.getOrCreateInstance(el));
  document.addEventListener('livewire:navigated', () => initTips());
  Livewire.hook('morph.updated', ({ el }) => initTips(el));
</script>
```

Left-over `.modal-backdrop` after navigation: hide the modal first, then navigate on `hidden.bs.modal`; never remove the backdrop by hand.

## jquery-bridge

With jQuery on `window`, BS5 also registers `$.fn.modal` and the like. That keeps legacy code alive. When no code calls them any more, put `data-bs-no-jquery` on `<body>`, then drop jQuery if nothing else needs it (DataTables and Select2 still do).

## http-asset, unpinned, no-sri

Pin exact versions (`bootstrap@5.3.9`), use https, and add `integrity` + `crossorigin` (`templates/cdn-tags.html`, hashes checked against jsDelivr). `bootstrap@5` or `@latest` can change the page under you; 6.0 is alpha and breaks class names.

## z-index (no doctor code; the usual stacking bug)

Bootstrap's scale, in order:
- dropdown 1000;
- sticky 1020;
- fixed 1030;
- offcanvas backdrop 1040;
- offcanvas 1045;
- modal backdrop 1050;
- modal 1055;
- popover 1070;
- tooltip 1080;
- toast 1090.

A fixed header must stay at or below 1030. If a theme puts its header at 9999, modals open under it. Change the Sass map as a whole (`$zindex-*`), never one element with an ad-hoc number.
