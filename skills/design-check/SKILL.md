---
name: design-check
description: Use when the user wants to verify their app's UI matches a design system — either their own adopted DESIGN.md or any brand from the awesome-design-md catalog (Linear, Stripe, Notion, etc.). Triggers on "check if our design matches", "is the theme respected", "find design conflicts", "how close is our app to Linear", "compare our design to Stripe". Read-only conformance scan that compares actual code against a reference design system and reports every mismatch with file:line references. Does NOT edit code — hands off to /normalize for fixes. Pipeline position — Step 2 of the design workflow chain. Upstream: design-md (after brand adoption), USER (direct invocation). Downstream: normalize (auto-offers handoff at end of scan). Full chain: design-md → design-check → normalize → polish → audit → finishing-a-development-branch.
user-invocable: true
argument-hint: "[scope] [--against <brand>]"
allowed-tools: Bash Read Grep Glob Skill
---

# design-check — verify the app respects a design system

**Read-only** conformance scan. Supports two modes:

- **Mode A — Self check:** compare the app against its own adopted design system (`DESIGN.md`, tailwind config, tokens, or CSS vars). Answers _"Is our theme respected?"_
- **Mode B — Benchmark:** compare the app against any brand from the [awesome-design-md](https://github.com/VoltAgent/awesome-design-md) catalog without modifying the project. Answers _"How close is our app to Linear / Stripe / Notion?"_

Both modes are **read-only**. Neither writes code. Fixes go through `/normalize`.

## When to use

- After adopting a design system via `/design-md` and want to know what needs fixing
- Before merging a feature branch, to catch design drift early
- During refactors, to see how far the app has drifted from its own tokens
- When onboarding to an unfamiliar codebase, to see the design system map vs reality

## When NOT to use

- To **fix** drift → use `/normalize` instead
- For a11y / perf / responsive audits → use `/audit` instead
- To **create** a new design system → use `/design-md` or `/frontend-design`

## Invocation

| Command | Mode | Meaning |
|---|---|---|
| `/design-check` | A | Full app, compared against own design system |
| `/design-check src/app` | A | Narrowed scope, own design system |
| `/design-check --against linear.app` | B | Full app, compared against Linear |
| `/design-check src/app --against stripe` | B | Narrowed scope, compared against Stripe |
| `/design-check --benchmark` | B | Runs against every brand in the catalog and ranks closest → furthest |

## Steps

### 0. Parse the arguments

Split the argument string into `scope` and optional `--against <brand>` / `--benchmark`. If `--against` is present, switch to **Mode B**. If `--benchmark` is present, switch to **Mode B** in ranking mode. Otherwise **Mode A**.

### 1. Resolve the reference design system

#### Mode A — the app's own source of truth

Check in this order of precedence and stop at the first hit:

| Priority | Source | Check command |
|---|---|---|
| 1 | `DESIGN.md` (from `/design-md`) | `test -f <root>/DESIGN.md` |
| 2 | `tailwind.config.{js,ts,mjs,cjs}` | `ls <root>/tailwind.config.*` |
| 3 | Token file | `find <root> -maxdepth 3 -name "tokens.*" -o -name "design-tokens.*"` |
| 4 | CSS custom properties | `grep -l -- "--color-\|--font-\|--space-" <root>/**/*.css` |
| 5 | Style guide doc | `find <root> -maxdepth 3 -iname "style*guide*.md" -o -iname "design-system*.md"` |

Print the detected source: `Reference design system (own): <source> (<relative-path>)`.

If none exist, stop and say: **"No design system detected. Run `/design-md <brand>` to adopt one, or use Mode B: `/design-check --against <brand>` to benchmark against a catalog brand."**

#### Mode B — a brand from the awesome-design-md catalog

Fetch the reference DESIGN.md into a temporary location — **never write it to the project root** (that would mutate the user's source of truth). Use `/tmp/design-check-<brand>.md`:

```bash
brand="<brand>"
tmpfile="/tmp/design-check-${brand}.md"
mkdir -p /tmp
cd /tmp && rm -f DESIGN.md && npx --yes getdesign@latest add "$brand" >/dev/null 2>&1
mv /tmp/DESIGN.md "$tmpfile" 2>/dev/null
test -f "$tmpfile" && echo "Reference design system (benchmark): $brand → $tmpfile"
```

If the brand is not in the catalog, list available brands via:

```bash
gh api repos/VoltAgent/awesome-design-md/contents/design-md --jq '.[].name'
```

…and ask the user to pick one.

**Benchmark sub-mode (`--benchmark`):** fetch all 58+ brands once into `/tmp/design-check-catalog/`, then run step 2-4 against each, and rank by conflict count (fewest conflicts = closest match). Warn the user this takes a few minutes and costs tokens. Only run if explicitly requested.

### 2. Extract the expected tokens

Read the detected source and extract four sets:

- **Colors** — hex values + semantic names (primary, accent, surface, text, border, status...)
- **Fonts** — family names + weights + sizes + letter-spacing
- **Spacing** — the scale (4/8/12/16… or custom)
- **Radii / shadows** — named tokens if the source defines them

For `DESIGN.md`, scan sections like "Color Palette", "Typography Rules", "Spacing". For `tailwind.config`, read the `theme.extend` block. For CSS vars, scan the `:root` block.

Present these as a compact table to the user so they can confirm the extraction is correct before scanning.

### 3. Scan the codebase for actual usage

Scope: the argument passed to the skill (e.g. `src/app`), or the full `src/` + `app/` + `components/` tree if no scope was given.

**Run these checks in parallel** using Grep/Glob:

#### 3a. Color conflicts

```bash
# Hardcoded hex colors
rg -n --type typescript --type js --type css '#[0-9a-fA-F]{3,8}\b' <scope>

# Hardcoded rgb/rgba/hsl
rg -n '\brgba?\(|\bhsla?\(' <scope>

# Arbitrary Tailwind color values
rg -n '(bg|text|border|ring|fill|stroke|from|to|via)-\[#' <scope>

# Tailwind color names outside the allowed palette (e.g. bg-purple when palette has no purple)
rg -n '(bg|text|border)-(slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose)-[0-9]' <scope>
```

For each hit, compare the value against the palette extracted in step 2. If the value is **not** in the palette (or the semantic name doesn't map to one), record a conflict.

#### 3b. Typography conflicts

```bash
# font-family declarations
rg -n 'font-family\s*:' <scope>

# Arbitrary Tailwind font values
rg -n "font-\[" <scope>

# Hardcoded font-size
rg -n 'font-size\s*:' <scope>
rg -n 'text-\[' <scope>

# Font weights outside the scale
rg -n 'font-(thin|extralight|light|normal|medium|semibold|bold|extrabold|black)' <scope>
```

Record a conflict for any font family / size / weight not declared in DESIGN.md's Typography section.

#### 3c. Spacing conflicts

```bash
# Arbitrary Tailwind spacing values
rg -n '(p|m|gap|space|top|left|right|bottom)-\[' <scope>

# Hardcoded pixel/rem values in inline styles
rg -n '(padding|margin|gap|top|left|right|bottom)\s*:\s*[0-9]+(px|rem|em)' <scope>
```

Compare against the spacing scale. Values outside the scale are conflicts.

#### 3d. Radii / shadow conflicts

```bash
rg -n '(rounded|shadow)-\[' <scope>
rg -n 'border-radius\s*:|box-shadow\s*:' <scope>
```

### 4. Produce the conformance report

Print a structured report in this exact shape:

```markdown
## Design Conformance Report

**Mode:** <Self check | Benchmark vs <brand>>
**Reference:** <source> (<relative-path or /tmp path>)
**Scope:** <scope>
**Scanned:** <N> files

### Color conformance: <✓ pass | ⚠ N warnings | ❌ N conflicts>

<Only list conflicts — one line each:>
- `src/components/Button.tsx:12` — `bg-purple-500` (not in palette; closest match: `bg-[#5e6ad2]` — Brand Indigo)
- `src/app/page.tsx:45` — `#ff0000` (hardcoded hex; suggest semantic status token)

### Typography conformance: <status>

- `tailwind.config.ts:18` — font-family `"Space Grotesk"` not declared in DESIGN.md (expected: `Inter Variable`)
- `src/app/hero.tsx:33` — `text-[19px]` (not in type scale; nearest: `text-xl` = 20px)

### Spacing conformance: <status>

- `src/components/Card.tsx:8` — `p-[13px]` (not in spacing scale; nearest: `p-3` = 12px or `p-4` = 16px)

### Radii / shadow conformance: <status>

### Summary

| Dimension | Status | Conflicts |
|---|---|---|
| Color | ❌ | 7 |
| Typography | ⚠ | 2 |
| Spacing | ✓ | 0 |
| Radii/Shadow | ✓ | 0 |

**Overall:** <PASS | WARN | FAIL>
**Similarity score (Mode B only):** <0-100%> — (100 - conflict_count * penalty), clamped to 0.

**Fix with:** `/normalize <scope>` — will auto-align conflicts to the design system.
```

For **benchmark mode**, also emit a ranking table when `--benchmark` is used:

```markdown
### Closest brands to your app

| Rank | Brand | Conflicts | Similarity |
|---|---|---|---|
| 1 | linear.app | 12 | 88% |
| 2 | vercel | 18 | 82% |
| 3 | notion | 24 | 76% |
```

### 5. Offer the handoff

**Mode A:** ask exactly once: **"Run `/normalize <scope>` to auto-fix these conflicts?"** If yes, invoke `/normalize` via the Skill tool. If no, stop.

**Mode B:** ask exactly once: **"Adopt `<brand>` as your design system? This will run `/design-md <brand>` and replace any existing DESIGN.md."** If yes, invoke `/design-md` via the Skill tool with the brand. If no, delete `/tmp/design-check-*.md` and stop.

## Severity rules

| Severity | Meaning | Examples |
|---|---|---|
| **P0 (blocker)** | Hardcoded color/font not in the design system, visible in user-facing UI | `#ff0000` in a button, custom font in a heading |
| **P1 (conflict)** | Tailwind class outside the declared palette | `bg-purple-500` when palette has no purple |
| **P2 (drift)** | Arbitrary value that happens to visually match a token | `text-[16px]` (matches `text-base` = 16px) |
| **P3 (cosmetic)** | Shadow/radius not matching named tokens exactly | `rounded-[6px]` vs `rounded-md` = 6px |

P0 and P1 are real conflicts that must be fixed. P2 and P3 are warnings that can be batch-normalized later.

## Integration with other skills

| Skill | How design-check connects |
|---|---|
| `/design-md` | Adopts the DESIGN.md that design-check uses as source of truth |
| `/frontend-design` | Builds UI grounded in DESIGN.md (prevents drift at creation) |
| `/normalize` | Fixes the conflicts design-check reports |
| `/audit` | Complements — audit covers a11y/perf, design-check covers theme conformance |
| `/kb-query` | Can answer "what does DESIGN.md say about button colors?" mid-scan |

## Notes

- **Read-only.** This skill never edits code. If the user wants fixes, hand off to `/normalize`.
- **Token discovery is heuristic.** If DESIGN.md exists, always prefer it. Tailwind config and CSS vars are fallbacks.
- **Scope matters.** Scanning `src/` with 1000+ files is expensive — ask the user to narrow if they don't specify.
- **False positives are expected** on P2/P3. The P0/P1 findings are the ones that actually matter.
- **Semantic matching beats exact matching.** `bg-[#5e6ad2]` and `bg-indigo-600` can be the same color — dedupe by resolved hex, not by string.
