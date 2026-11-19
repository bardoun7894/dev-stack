---
name: bootstrap-ui
description: Bootstrap 5.3 apps (and admin themes built on Bootstrap, like Metronic, AdminLTE, CoreUI and Pixinvent) - find and fix conflicts, then make the UI look current. Includes a read-only doctor for mixed Bootstrap versions per layout, double CSS/JS, BS4 CSS with BS5 JS, BS3/BS4 classes and data-toggle on BS5 pages, RTL pages without the RTL build, Tailwind preflight and class clashes, !important wars, unpinned CDN assets, and Livewire re-render issues. Also includes a BS3/BS4 to BS5 migration map, a Sass theme and a CDN theme (light, dark, RTL Arabic) checked for WCAG contrast, and a kitchen-sink before/after render. Use for "bootstrap", "bs5", "bootstrap 5", "bootstrap 4", "metronic", "adminlte", "coreui", "bootstrap conflict", "bootstrap and tailwind", "upgrade bootstrap", "bootstrap rtl", "bootstrap dark mode", "bootstrap theme", "make the bootstrap ui better/modern", and Darija/Arabic "بوتستراب", "bootstrap فيه مشاكل", "حسن الواجهة ديال bootstrap". Not for Tailwind-only or design-system work without Bootstrap (unslop, frontend-design, design-md).
---

# bootstrap-ui

Bootstrap mechanics only. The split with the other skills:
- overall aesthetic direction: `frontend-design` / `unslop`;
- a brand look borrowed from Linear, Stripe and the like: `design-md`, checked with `design-check`;
- Arabic copy: `arabic-ui`.

Use this skill to make those choices work in a Bootstrap app without conflicts.

Everything here was checked on 2026-11-19:
- against the npm dist of bootstrap 5.3.9 (latest) and 4.6.2;
- against real Tailwind 3.4.17 and 4.1.11 builds;
- on the owner's apps (beldify admin, abd, hany-pos).

6.0.0-alpha.1 exists on npm `next`; do not use it for client work.

## Files

| Path | What |
|---|---|
| `scripts/bs_doctor.py PATH [--out DIR] [--json] [--exclude GLOB] [--only CODE]` | Read-only conflict scan; exit 1 when a high finding exists |
| `scripts/contrast.py THEME.css [BASE.css]` | WCAG check of a theme, light and dark; exit 1 on a failing text pair |
| `scripts/kitchen_sink.py --css A --css B [--theme dark] [--dir rtl] --out page.html` | One admin screen to render a theme before and after |
| `scripts/gen_migration.py` | Regenerates `references/migration.md` from the doctor's rule data |
| `references/conflicts.md` | Cause and fix for every doctor code, Tailwind clash table, Livewire recipe, z-index |
| `references/migration.md` | BS3/BS4 to BS5 class and attribute map, sed recipes |
| `references/theming.md` | Sass vs CSS path, color modes, RTL and Arabic fonts, verification |
| `references/look.md` | What makes Bootstrap look default, layout patterns, accessibility |
| `templates/theme.scss` | Sass theme (brand block + house look + dark) |
| `templates/bs-theme.css` | Runtime theme for CDN apps; re-points the 23 hard-coded primary spots |
| `templates/cdn-tags.html` | Pinned 5.3.9 tags with SRI (checked against jsDelivr), Blade LTR/RTL switch |
| `templates/color-mode.js` | Light/dark/auto toggle without flash |

Run scripts with `python3 ~/.claude/skills/bootstrap-ui/scripts/<name>` (stdlib only, Python 3.10+).

## Rules

1. Doctor first. Never theme or "modernise" a Bootstrap app before `bs_doctor.py` is clean of high findings. Styling over two Bootstrap builds, or over BS4 markup on BS5, hides the real bug.
2. One Bootstrap per layout, with JS of the same major as the CSS. Admin theme bundles already contain Bootstrap.
3. Never edit Bootstrap's or the theme's dist files. Overrides go in one file of our own, loaded last: the Sass theme, `bs-theme.css`, or the app's `app-ui.css`.
4. Tokens before `!important`. Add `!important` only where a measured theme rule forces it, and write the reason next to it.
5. RTL: logical classes only (`ms/me/ps/pe`, `text-start/end`), the `.rtl` CSS when `dir="rtl"`, an Arabic font first under `[dir=rtl]`, and no letter-spacing on Arabic.
6. Every theme change passes `contrast.py` (text at 4.5:1 or better, light and dark). The owner sees before and after screenshots (stock vs themed, plus dark and RTL when the app has them) before it ships.
7. Client repos follow the server-first rule and their own branch, spec and deploy question. Run the doctor read-only anywhere. Edits need the owner's go for that repo.

## W1. Diagnose

```bash
python3 ~/.claude/skills/bootstrap-ui/scripts/bs_doctor.py /root/<app> --out ~/bs-audits/<app>/<date>
```

The doctor works out, per layout, which Bootstrap CSS and JS each page really loads:
- links, `asset()`, `@vite` entries;
- Blade `@extends`, `<x-*-layout>` and `@include` (one level);
- versions read from CDN URLs, local file headers and `package.json`;
- monorepos with several `resources/views` roots.

Then it reports findings `F1..Fn` sorted high first, each with file:line samples. Partials included under `@if` (for example `head` vs `head_ar`) count as alternatives, not double loads.

Spot-check about 5 samples of every high finding in the files before you report them. Then report to the owner with codes, splitting the findings into:
- breaks now: mixed versions, JS/CSS mismatch, data-toggle, RTL CSS, Tailwind preflight;
- looks wrong: class migration;
- hygiene: `!important`, inline hex, SRI.

## W2. Fix conflicts (order matters)

1. `mixed-versions`, `double-css`, `double-js`, `js-css-mismatch`: one Bootstrap per layout (`conflicts.md`).
2. `tw-preflight`, `tw-clash`: separate layouts, or prefix + no preflight (`conflicts.md`, v3 and v4 recipes verified).
3. `rtl-css`: one CSS chosen by the same variable as `dir` (`templates/cdn-tags.html`).
4. `data-toggle`, then `bs4-class` / `bs3-class`: `migration.md` sed recipes on a branch, run the doctor again, read the diff, check the pages in LTR and RTL.
5. `old-minor` (5.0 to 5.2): upgrade to 5.3.9 before theming. Color modes, `*-subtle`, `text-bg-*` and `focus-ring` are 5.3+.
6. `rerender`: Livewire/Alpine recipe in `conflicts.md`.

Run the doctor again after each step. Paste its findings line in the report.

## W3. Theme

- **Build step:** copy `templates/theme.scss`, change only the BRAND block, compile, then run `contrast.py` on the output.
- **CDN app:** pin the tags from `templates/cdn-tags.html`, copy `templates/bs-theme.css` after Bootstrap, change the BRAND block, keep each `*-rgb` triplet equal to its hex, then run `contrast.py bs-theme.css bootstrap.min.css`.
- **Admin theme (Metronic, AdminLTE):**
  1. count class usage first;
  2. override the top selectors through tokens in one `app-ui.css`;
  3. keep semantic colors semantic.

  This follows KB [[abd/bootstrap-brand-recolor]].
- **Dark mode:** `templates/color-mode.js`, inline at the top of `<head>`.

## W4. Polish components

Apply `references/look.md`:
- page header pattern;
- stats row;
- table in a card (muted headers, `text-end font-monospace` amounts, `badge text-bg-*` status);
- form layout and validation;
- modals;
- one icon set.

For a direction beyond the house look (a brand personality), get it from `frontend-design` or `unslop`, then express it through the same tokens.

## W5. Verify and show

```bash
S=~/.claude/skills/bootstrap-ui/scripts
python3 $S/contrast.py <theme.css> [bootstrap.min.css]
python3 $S/kitchen_sink.py --css <bootstrap.min.css> --out before.html
python3 $S/kitchen_sink.py --css <bootstrap.min.css> --css <theme.css> --out after.html
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new --window-size=1360,1180 \
  --hide-scrollbars --virtual-time-budget=4000 --screenshot=after.png file://$PWD/after.html
```

Look at the screenshots yourself first, then show them. Better still, screenshot the client's own pages on the dev site. The doctor must show no high findings, and `contrast.py` must exit 0.

## Tests

`cd ~/.claude/skills/bootstrap-ui/scripts && python3 -m unittest test_bootstrap_ui -v` runs offline on fixture projects. It covers version per layout, `@if` alternatives, Blade `asset()` refs, data-toggle split, BS5-on-BS4, RTL, Tailwind preflight from compiled CSS, contrast math, and the migration doc staying in sync.
