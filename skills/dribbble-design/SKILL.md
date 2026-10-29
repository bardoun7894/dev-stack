---
name: dribbble-design
description: "Design inspiration research from Dribbble (plus Behance / Mobbin / Awwwards via web search) for a screen, module, or whole app — web or mobile. Searches Dribbble headlessly, downloads reference shots into design/inspiration/<date>-<slug>/ with a manifest, analyzes them against the project's DESIGN.md, and writes an inspiration REPORT.md that feeds frontend-design / agy-delegate / design-check. Triggers: \"find designs on Dribbble\", \"dribbble inspiration for X\", \"get reference images for the Y screen\", \"what does a good Z look like\", \"find a better design for our app\", \"mood board\", \"UI references\", \"/dribbble-design\"."
user-invocable: true
argument-hint: "<what you need inspiration for> [--type mobile|web] [--limit N] [--full]"
allowed-tools: Bash Read Write Skill WebSearch WebFetch
---

# dribbble-design — reference research, not copying

Turns "find a better design for our X" into: a curated folder of reference shots on disk,
a written analysis of what those shots do well, and a concrete brief for whoever builds the UI.
Inspiration only. Nothing downloaded here ships as a product asset.

Why headless: Dribbble's v2 API has no search endpoint and dribbble.com sits behind an
AWS WAF JavaScript challenge (plain `curl` gets an empty HTTP 202). `scripts/dribbble.mjs`
drives the system Chrome/Chromium through `playwright-core` (no browser download) and works
on macOS (Google Chrome) and Linux servers (`/usr/bin/chromium-browser`).

## Steps

### 0. Log and ground

- `/kb-spec log "dribbble research: <subject>"` (standing rule).
- `/kb-query "<subject> design decisions"` — prior mood boards, DESIGN.md decisions, rejected
  directions. Do not redo research the KB already has.
- Load the project's design truth, in this order, first that exists:
  `DESIGN.md` → `design/DESIGN-BRIEF.md` + `design/references.md` → a project skill such as
  `.agents/skills/*design-system*/SKILL.md` → nothing (fall back to
  `references/dribbble-ui-skills.md` as a neutral light-mode baseline, and say so).

### 1. Turn the ask into 3–5 queries

Dribbble search is tag-driven. Good queries are `<domain> <screen> <platform>`:
`fashion app onboarding mobile`, `ai design studio dashboard`, `credits pricing page saas`,
`ecommerce product detail arabic`. Add `--type mobile` or `--type web-design` when the platform
is known; use `--sort recent` for trends, default `popular` for proven patterns. Note the
platform of the project (web SaaS vs mobile PWA) before choosing.

### 2. Run the legs in parallel

- **Dribbble (primary):**
  ```bash
  S=~/.claude/skills/dribbble-design/scripts
  node $S/dribbble.mjs search "fashion app onboarding" --type mobile --limit 12
  node $S/dribbble.mjs fetch  "fashion app onboarding" --type mobile --limit 8 --full
  ```
  `search` prints title / author / url / image (add `--json` for scripting). `fetch` downloads
  the top N to `<project-root>/design/inspiration/<YYYY-MM-DD>-<slug>/` and writes
  `manifest.json` + `README.md`. `--full` opens each shot page and grabs every screen of
  multi-screen case studies. `download <url|id>...` fetches specific shots the user pasted.
  `doctor` checks the browser + dependency. First run installs `playwright-core` into `scripts/`.
  **Point every query of one packet at the same `--out` folder**: the manifest merges, numbering
  stays continuous across queries, and a shot already saved is skipped rather than duplicated.
- **Wider web (secondary):** `web-search "dribbble <query>"` (SearXNG, fall back to the
  `WebSearch` tool), and the same for `behance <query>`, `mobbin <query>`, `awwwards <query>`.
  Search engines behind SearXNG ignore the `site:` operator, so put the platform name in the
  query and filter results by domain yourself. See `references/sources.md`.
- **KB leg** already ran in step 0.

Cap: at most 5 pages and 40 downloads per query. Keep the default delays. Do not loop this in
a cron. If a page returns no cards, the WAF may be rate-limiting: stop, wait, do not retry
in a loop.

### 3. Look at the images

Use the `Read` tool on the downloaded files (it renders images). For every shot note in one
line each: layout skeleton, navigation model, card/surface treatment, type hierarchy, palette
and accent usage, imagery style, motion cues (video flag in manifest), and the one thing it
does better than our current screen. Prefer shots with views in the thousands (like counts are
often hidden for logged-out visitors; `--min-likes N` uses likes or views, whichever is present)
and shots from studios that post case studies (`--full` gives the full flow).

### 4. Write `REPORT.md` next to the images

Use `references/report-template.md`. Sections: subject and queries; reference table (id,
author, url, file, why it matters); findings `F1..Fn` (patterns seen across ≥ 2 shots);
recommendations `R1..Rn` mapped to our tokens and components (adopt / adapt / reject, each
with the project rule that decides it, e.g. RTL logical utilities, imagery policy, radius
scale); risks (over-decoration, low contrast, trend churn); hand-off brief.
Never propose copying a shot one-to-one, and never propose using a downloaded image in the
product.

**Copy every author name and shot URL out of `manifest.json`, never from memory and never from text
visible inside the image.** A screenshot's own UI often shows a person's name that is not the author,
and a recalled name is a fabricated credit attached to a real person. Read the manifest fields into
the table, then diff the finished table back against the manifest before you call the report done.

### 5. Hand off and mirror

- UI implementation → `agy-delegate` (project rule where present) or `/frontend-design`,
  brief = REPORT.md hand-off section + image paths. Follow with `/design-check` → `/normalize`
  → `/polish` → `/audit`.
- `/kb-docs-sync` so `REPORT.md` lands in the KB; `/kb-spec log done`.
- If the project has no DESIGN.md yet, suggest `/design-md <closest brand>` or a design packet
  that turns the report into `design/DESIGN.md`.

## CLI reference

```
node dribbble.mjs search   "<q>" [--type mobile|web-design|product-design|branding|all]
                                 [--sort popular|recent] [--pages 1-5] [--limit 1-40] [--json]
node dribbble.mjs fetch    "<q>" [same flags] [--out DIR] [--full] [--min-likes N]
node dribbble.mjs download <shot-url|id> [...] [--out DIR]
node dribbble.mjs doctor
```

Env: `DRIBBBLE_BROWSER=/path/to/chrome` overrides browser detection (default: Google Chrome on
macOS, `chromium-browser`/`chromium`/`google-chrome` on Linux, then any `ms-playwright` cache).
Output default: `<project-root>/design/inspiration/<date>-<slug>/`; project root = nearest
ancestor with `.git/` or `.claude/`, never `$HOME`.

## Rules

- Reference use only, per Dribbble's terms. Low volume, human-paced, no scheduled scraping.
- `design/inspiration/**` is commit-able (small webp renders) but the images are third-party:
  keep `manifest.json` next to them, never move them into `public/` or `storage/`.
- Real-person photos in references are fine to look at; the project's own imagery policy
  (for FashionVerse: garments, not people) governs what we build.
- Report findings as `F1..`, recommendations as `R1..`, and keep the codes across the session.
- No completion claim without the `fetch` output and `ls` of the folder pasted.

## Files

- `scripts/dribbble.mjs` — the CLI (Node 18+, ESM). `scripts/package.json` pins `playwright-core`.
- `references/dribbble-ui-skills.md` — Dribbble's own UI token set (vendored from
  `ihlamury/design-skills`, MIT) — neutral light-mode baseline and an example of what a
  token-level design skill looks like.
- `references/sources.md` — other inspiration sources and how to query them.
- `references/report-template.md` — REPORT.md skeleton.
