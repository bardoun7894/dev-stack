# Inspiration sources beyond Dribbble

All of these are reference-only. Credit authors, never ship their assets.

| Source | Best for | How to reach it from here |
|---|---|---|
| Dribbble | Visual direction, single screens, motion teasers, fast trend read | `scripts/dribbble.mjs` (headless). No public search API since v2. |
| Behance | Full case studies, multi-screen flows, branding systems | `web-search "behance <query>"` / `WebSearch site:behance.net <query>`; open project URLs with `WebFetch` for text; images need a browser (Playwright) — reuse the `openBrowser` pattern in `dribbble.mjs` if a Behance fetcher is ever needed. |
| Mobbin | Real shipped mobile/web flows, screen-by-screen | Login-gated. Use `WebSearch "mobbin <app> <flow>"` for the public preview pages; do not scrape. |
| Awwwards | Marketing sites, motion-heavy landing pages | `WebSearch "awwwards <query>"`; `WebFetch` the site-of-the-day pages for tech notes. |
| Godly / Land-book / Lapa Ninja | Landing page layouts | `WebSearch "<site> <query>"`; `WebFetch` for lists. |
| Pinterest | Mood boards, fashion editorial, palettes | `WebSearch "pinterest <query>"` only; heavy anti-bot, do not scrape. |
| SaaS UI galleries (Refero, Page Flows, UI Sources) | Onboarding, pricing, settings, empty states | `WebSearch`. |
| `awesome-design-md` (`/design-md`) | Token-level brand systems (Linear, Stripe, Notion, …) | `/design-md list` |
| `ihlamury/design-skills` | 87 token-level UI skills extracted from real products | `npx skills add ihlamury/design-skills --skill <name>-ui-skills` (project-local install), or `gh api -H "Accept: application/vnd.github.raw" repos/ihlamury/design-skills/contents/skills/<name>/SKILL.md`. Names: `gh api repos/ihlamury/design-skills/contents/skills --jq '.[].name'`. |

## Query patterns that work

- `<domain> <screen> <platform>`: `fashion app onboarding mobile`, `saas credits pricing page`.
- `<style> <component>`: `editorial product card`, `pill navigation dashboard`.
- Arabic / RTL: `arabic app ui`, `rtl dashboard`, `arabic ecommerce` (thin on Dribbble; Behance
  has more Gulf/Levant studios).
- Fashion-specific: `fashion ecommerce app`, `clothing store app`, `ai fashion`, `virtual try on`,
  `lookbook`, `garment design tool`, `moodboard app`, `pattern maker`.

## SearXNG note

The dev-stack SearXNG instance (`web-search`, MyContabo `100.64.0.1:8888`) aggregates Bing /
DuckDuckGo / Brave for the `general` and `images` categories. Those engines drop the `site:`
operator, so `site:dribbble.com` returns unrelated results. Put the platform name in the query
and filter by domain in the results instead. The harness `WebSearch` tool honors `site:`.
