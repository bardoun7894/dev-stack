---
name: market-swot
description: "SWOT + competitor research + UI/UX/motion direction + personal brand. Triggers: \"swot\", \"competitor analysis\", \"compare with similar apps/websites\", \"make the UI more professional/catchy like X\", \"personal brand\", \"analyze me\", \"تحليل سوات\", \"منافسين\", \"براند شخصي\", \"audit our design\", \"what is outdated in the UI\", \"update the design\", \"راجع التصميم\", \"شو قديم بالتصميم\", \"/market-swot\". Modes: project (startup/app SWOT, competitors, feature gaps, UI/UX + motion), me (personal-brand SWOT for Mohamed Bardouni), audit (design audit vs current practice), refresh (update the skill's own knowledge). Ends in a HARD STOP for owner approval."
user-invocable: true
argument-hint: "project [<path>] | me | audit [<path>] [--url <live-url>] | refresh"
allowed-tools: Bash Read Write Skill WebSearch WebFetch Agent
---

# market-swot — evidence-based positioning, not copying

Modes: `project [<path>]` (startup/app SWOT), `me` (personal-brand SWOT for Mohamed Bardouni), `audit [<path>] [--url <live-url>]` (design audit) and `refresh` (self-refresh only, then stop).
Codes (keep for the whole session): S1.. W1.. O1.. T1.. (SWOT), SO/ST/WO/WT (TOWS), F1.. (feature gaps: adopt/adapt/skip),
R1.. (UI/UX + motion recommendations), A1.. (personal-brand actions), I1.. (audit issues, P0-P3), D1.. (outdated items), U1.. (update plan).

## Rules

- Low-volume, human-paced browsing. No login scraping (LinkedIn/Mostaql: public pages or URLs the owner gives).
- Never copy a competitor UI or asset one-to-one. Inspiration only.
- Names and URLs only from fetched data. Every claim cites a repo path or a URL; unprovable items are dropped.
- Jev labels and scores, the LLM never sorts lists (`jev score` / `jev choice`).
- Website projects run on MyContabo per `where-to-work`; pure web research may run on the Mac.

## Steps

### 0. Freshness, log and ground
Run `bash scripts/freshness.sh` first, before any mode (stale = stamp older than 7 days or missing; env FRESH_MAX_DAYS).
If anything is stale, run step 4b first, then update the "AI-era UI/UX" section of `references/uiux-motion.md`: add new items
with URL and date, move items whose sources are older than 12 months into its "Archived" list (never delete), bump
`last_refreshed`, and show the owner a one-line diff summary. No cron, no loops: this runs only when the skill is used.
Mode `refresh`: do only this using steps 4b + 4c(b) only (no Chrome in headless runs), then stop.

`/kb-spec log "market-swot: <subject>"`, `/kb-query "<subject> competitors positioning design"`, `check-project-inbox`.
Skip research the KB already has.

### 1. Inventory (zero AI)
- project: `bash scripts/inventory.sh <repo>` (name, readme, PRD, specs, stack, routes/screens, pricing, i18n, DESIGN.md).
- me: `bash scripts/me-inventory.sh` (portfolio content, GitHub repos, projects dir, memory index).

### 2. Candidates
`web-search` (SearXNG; it ignores `site:`, so put the platform name in the query), fallback WebSearch. Find 5-8 close
competitors, rank with `jev score` / `jev choice`, keep the top 3-5.

### 3. Research worker (one pass)
`jdelegate --no-auto-mcp --no-auto-skill --no-auto-role --role researcher "<references/researcher-brief.md, filled>"`.
It writes competitors.json and the matrix section only (shape: `references/competitor-matrix.md`).

### 4. Area-leader UI/UX study
Besides direct competitors, study the UI/UX of the 3-5 best websites that SPECIALISE in the project's area (category
leaders). In `me` mode: the best personal-brand sites of developers/designers/agencies in the same niche. Add expert
method sources (`references/sources.md`). Cover these showcase platforms explicitly:
- Dribbble: `dribbble-design` scripts, 2-3 queries, all into the same `--out` folder.
- Behance, Mobbin, Awwwards, Godly, Land-book: `web-search` with the platform name in the query, then WebFetch the pages.
Capture screenshots into `<report>/screenshots/`.

### 4b. Fresh practices (last 7 days)
Before synthesis, find the newest website UI/UX and app UI/UX best practices published in the past week, with AI-assisted
design as a focus: AI UI tools, generative UI, AI-native patterns, motion. Run 3-4 queries with `web-search` and
WebSearch, adding the current month and year to each query. Keep only sources dated within 7 days. Save them as
`<report>/fresh-<date>.md` with a URL and date for every item. Feed them into R1.. and tag each such recommendation `fresh`.
Weekly sources: see "Weekly fresh" in `references/sources.md`.

### 4c. X (Twitter) pulse
Two sources, merged into `<report>/x-posts-<date>.md` (URL, author handle, date and text exactly as shown):
a) claude-in-chrome on x.com search in the owner's logged-in Chrome: Latest tab, query + `since:<date-7d>`, read at most ~30 posts.
   Read only; never like, follow or post. If Chrome is not connected (e.g. headless), skip and say so.
b) `web-search "x.com <topic> <month year>"` (SearXNG) for public posts.
Then `bash scripts/x-summarize.sh <posts.md>` (Grok on Command Code via `pi -p`, summarizes only the given posts; it has no live X
search). Exit 3 "grok unavailable" (429/quota/empty): summarize in session instead. Feed themes into R1.. tagged `fresh`.

### 5. Synthesis (in session)
SWOT S/W/O/T, TOWS (SO/ST/WO/WT), feature gaps F1.. (adopt/adapt/skip), UI/UX + motion R1.. mapped to the project's
DESIGN.md tokens (checklists: `references/uiux-motion.md`), personal-brand actions A1.. (headline, bio, portfolio case
studies, GitHub pinned repos, LinkedIn/Mostaql post plan; follow `~/.claude/skills-parked/dev-profile-setup/SKILL.md`
"evidence first"). Scoring: `references/swot-startup.md` / `references/swot-personal.md`.

### 6. Outputs
`<project>/docs/market-swot/<YYYY-MM-DD>/REPORT.md` + `competitors.json` + `fresh-<date>.md` + `screenshots/`
(shape: `references/report-template.md`). `me` mode: `~/projects/portfolio-next/docs/brand-swot/<date>/`.
Then a private HTML page via the Artifact tool (load `artifact-design` first): SWOT 2x2 grid, competitor matrix,
screenshot gallery, ranked recommendations.

### 7. HARD STOP
Ask the owner which F/R/A codes to accept. Nothing touches specs before a yes.

### 8. After yes
Accepted codes -> `/kb-spec pre` -> `/speckit.specify` per new feature, or append to the existing
`specs/NNN/research.md`. UI items go to the project's UI worker rule (`agy-delegate`, or Claude workers where project
memory says so).

### 9. Capture
`/kb-docs-sync`, `/kb-spec log done`.

## When it runs
- On its own inside kb-dev Phase 2b for new products and UI-heavy work.
- The freshness check (step 0) on every run.
- Full SWOT or audit only on request.
- Weekly refresh via launchd: `bash scripts/install-weekly-refresh.sh` (`--dry-run` prints the plist, `--uninstall` removes it).

## Mode audit: `/market-swot audit [<path>] [--url <live-url>]`
Audits the design we already have against current online practice.
1. Evidence, zero AI: `bash scripts/design-audit.sh <repo> [url]` (dependency versions vs latest, Lighthouse and axe when a url is given and available else null, DESIGN.md + tokens file, old-pattern signals: jQuery, Bootstrap 3/4, old font stacks, `!important`, inline styles, missing prefers-reduced-motion, px-only spacing).
2. Screenshots of the live pages at desktop and mobile widths (`jev-browse` or claude-in-chrome).
3. Compare with fresh practices (step 4b), competitors and Dribbble/Behance references.
4. REPORT.md section "Design audit": issues I1.. (severity P0-P3, evidence file:line / URL / screenshot, why it matters); "Outdated" D1.. (what is old, what replaced it, source URL with date); "Update plan" U1.. ordered quick wins to deep changes.
5. Same HARD STOP (step 7) before anything goes into specs.

## Worked examples

**project mode, AI video SaaS.** Inventory the repo. Competitors: Synthesia, HeyGen, InVideo (confirm by search).
Area leaders: search "Awwwards AI video platform", "Godly AI SaaS landing", "Land-book video generator". Dribbble
queries "ai video generator dashboard" and "video editor timeline" (same --out); Behance via web-search "Behance AI video
generator dashboard UI". Fresh pass (4b): "AI UI patterns October 2026", "generative UI October 2026". Output R1.. such as
"timeline skeleton while render streams (fresh)", mapped to DESIGN.md tokens.

**me mode.** Run me-inventory. Queries "developer portfolio", "personal brand website" on Dribbble, Behance, Awwwards
(web-search with the platform name), plus 3 real developer portfolios found by search (fetch, do not guess URLs). Output
A1.. (headline, bio, case studies for shipped projects, pinned repos, LinkedIn/Mostaql plan) with evidence from
me-inventory.
