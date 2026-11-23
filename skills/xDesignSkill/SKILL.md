---
name: xDesignSkill
description: "Get the UI/UX design out of the latest X (Twitter) design posts for an idea, also when the closest post is about another kind of project (a healthcare dashboard as the reference for a transport dashboard). Reads the newest image and video posts of a watchlist of designer accounts, ranks them by closeness to the idea, saves the images at full size (cut into readable tiles, real colors sampled) and cuts videos into frames, then writes a design extract (tokens, layout, components, motion) mapped onto the user's own project for frontend-design / agy-delegate. Also takes pasted post links. Triggers: an x.com or twitter.com post link with \"do it like this\", \"design like this post\", \"get the design from this post\", \"latest dashboard designs on X\", \"check the last UI posts\", \"UI inspiration from X/Twitter\", \"/xDesignSkill\", and Darija/Arabic \"دير بحال هاد التصميم\", \"شوف آخر التصاميم ف X\", \"تصميم داشبورد بحال هادا\". Not for Dribbble/Behance research (dribbble-design)."
user-invocable: true
argument-hint: "<idea, e.g. \"transport fleet dashboard\"> | <x.com post url>... [--handles a,b] [--days N] [--limit N]"
allowed-tools: Bash Read Write Skill WebSearch
---

# xDesignSkill: design references from X posts

Turns "do a dashboard like the ones in this post" into three things on disk: the reference
posts (images and video frames), the measured facts about them (`manifest.json`), and a
design extract a builder can follow. The reference is for layout, hierarchy, tokens and
motion. The product gets its own content, brand and data.

How it reads X: X search needs a login, so the script does not search. It reads the newest
media posts of a watchlist of designer accounts through the public FxTwitter API (no key, no
login) and ranks them against the idea. A post found any other way goes in by link.

```bash
X=~/.claude/skills/xDesignSkill/scripts/xdesign.mjs
```

## Steps

### 0. Log and ground

- `/kb-spec log "x design research: <subject>"`.
- Load the project's design truth, first that exists: `DESIGN.md`, `design/DESIGN-BRIEF.md`,
  a project design-system skill. None: say so, the extract then proposes tokens.
- Note the project facts the reference must be mapped onto: business type, the 5 to 8 numbers
  or lists its main screen has to show, platform (web or mobile), languages (RTL or not).

### 1. Find the posts

The user pasted post links: go to step 2 with `download`.

Otherwise turn the ask into one idea string: subject words plus the screen type, with sibling
words for the subject (`"transport fleet logistics delivery dashboard"`). The screen type
(dashboard, mobile, landing) is what lets a post about another business still match.

```bash
node $X find "transport fleet logistics dashboard"            # ranked list, nothing saved
node $X find "transport fleet logistics dashboard" --days 30  # only the last 30 days
node $X latest uifoysal                                       # one account, newest first
```

Each line shows why it matched: subject words (3 points each), `type:dashboard` (2 points).
A post that matches only on type is the "close idea, other project type" case, and is a valid
reference. Nothing matches: add sibling words, add accounts (step 1b), or `--all` to list
every recent media post and pick by eye.

### 1b. Wider net (only when the watchlist is thin for this idea)

- Web search `<idea> dashboard UI design x.com` (`web-search`, else the `WebSearch` tool),
  keep the `x.com/<handle>/status/<id>` links, pass them to `download`.
- An account that posts this kind of work regularly: `node $X handles add <handle>` (checked
  against the API before it is saved to `~/.config/xdesign/handles.txt`).
- `node $X handles check` shows which accounts still answer and still post UI work.

### 2. Save them

```bash
node $X fetch "transport fleet logistics dashboard" --limit 6      # the top matches
node $X download https://x.com/uifoysal/status/2124547874956677451 # specific posts
```

Output: `<project-root>/design/inspiration/<date>-x-<slug>/` (`--out DIR` to override; point
every run of one job at the same folder, the manifest merges and numbering continues).

- `NN-<handle>-<id>.jpg`: the image at original size.
- `NN-...-t1..t4.jpg`: four overlapping tiles, made when the image is wider than 2600 px.
- `NN-...mp4`, `NN-...-fNN.jpg`, `NN-...-sheet.jpg`: the video, 6 to 16 frames spread over its
  length, and one contact sheet of those frames. `.mp4` files are git-ignored.
- `manifest.json`: per post the author, link, date, likes, views, file sizes and `palette`
  (dominant colors as hex with their share of pixels, sampled from the file, not estimated).
- `README.md`: the same as a table.

### 3. Look, in this order

Use `Read` on the files (it renders images).

1. The whole image or the video sheet: screen list, grid, where the eye goes first.
2. Every tile and the frames that differ: labels, numbers, spacing, radii, icon style, chart
   types, states. Read small text from the tiles, never guess it from the whole image.
3. For a video, compare consecutive frames: what changes, in what order, what stays still.
   That is the motion and interaction model (hover, filter change, drill-down, loading).

Colors come from `manifest.json` `palette`. A color too small to appear there (a thin accent,
a status dot) is written as "accent, about #xxxxxx (by eye)" so the builder knows it was not
measured.

### 4. Write `DESIGN-EXTRACT.md` next to the images

Use `references/extract-template.md`. It has two halves, and the second is the point:

- What the reference does: tokens, layout skeleton, component inventory, charts, motion.
- The same structure filled with this project's content: each reference widget mapped to a
  real number, list or action of the project, or dropped. A healthcare "Bed Occupancy" card
  becomes "Fleet in service" for a transport app; a widget with no counterpart is removed,
  not kept as decoration.

Then decisions `R1..Rn` (adopt / adapt / reject, each with the rule that decides it) and the
hand-off brief.

Copy author names and links from `manifest.json`, never from memory and never from text
visible inside an image.

### 5. Hand off

- Build: `agy-delegate` where the project rule says so, else `/frontend-design`
  (`/enterprise-dashboard` for data-heavy admin screens, `/dataviz` for the charts,
  `/arabic-ui` for RTL). Brief = the hand-off section + the image paths.
- After the build: `/unslop` or `/design-check` against the extract.
- `/kb-spec log done`.

## CLI

```
node xdesign.mjs find     "<idea>" [--handles a,b] [--days N] [--limit N] [--all] [--json]
node xdesign.mjs fetch    "<idea>" [same flags] [--out DIR] [--no-frames]
node xdesign.mjs latest   <handle>... [--limit N] [--json]
node xdesign.mjs download <post-url|id>... [--out DIR] [--subject "<text>"] [--no-frames]
node xdesign.mjs handles  [list | add <handle>... | rm <handle>... | check [<handle>...]]
node xdesign.mjs doctor
```

Node 18+, no npm packages. `ffmpeg` is needed for tiles, colors and video frames (without it
the files are still saved). Exit 3 = nothing matched or nothing to download.

## Limits to tell the user about

- Only watchlist accounts and pasted links are seen. A post by an unknown account is found
  through web search or by the user pasting it.
- About 20 to 25 newest media posts per account, nothing older.
- The API fails at random under load (404 or an empty list). The script tries three times per
  account and reports `no data`; that is not proof the account is gone. Run again later, do
  not loop.
- Caps: 30 accounts per run, 30 posts per run, video up to 240 s and 80 MB.

## Rules

- Reference only. Never ship a downloaded file, never reproduce a post one-to-one, never
  reuse its product name, logo, 3D art or copy. Credit stays in `manifest.json`.
- The project's own rules win over the reference: its DESIGN.md tokens, RTL, imagery policy,
  and the owner rule of no purple or violet gradients.
- Low volume, on request only. No cron, no bulk scraping of accounts.
- No completion claim without the `fetch`/`download` output and the folder listing.

## Files

- `scripts/xdesign.mjs`: the CLI. Tests: `node --test tests/xdesign.test.mjs` (dev-stack root).
- `references/designers.txt`: seed watchlist (one handle per line, `#` comments).
- `references/extract-template.md`: DESIGN-EXTRACT.md skeleton.
