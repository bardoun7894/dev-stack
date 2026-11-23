---
name: xDesignSkill
description: "Get the UI/UX design out of the latest X (Twitter) design posts for an idea, from any account, also when the best post is about another kind of project (a healthcare dashboard as the reference for a transport dashboard). Finds posts through X's own search (after a one-time login), Grok's X search, web search and a watchlist, ranks them by closeness to the idea and by likes and saves, shows a numbered gallery for the user to choose from, then saves the chosen posts (images at full size cut into readable tiles with real colors sampled, videos cut into frames) and writes a design extract (tokens, layout, components, motion) mapped onto the user's own project. Also takes pasted post links. Works in any agent that can run a shell command (Claude Code, Antigravity/agy, Codex, Gemini CLI, pi, OpenCode). Triggers: an x.com or twitter.com post link with \"do it like this\", \"design like this post\", \"get the design from this post\", \"latest dashboard designs on X\", \"check the last UI posts\", \"UI inspiration from X/Twitter\", \"/xDesignSkill\", and Darija/Arabic \"دير بحال هاد التصميم\", \"شوف آخر التصاميم ف X\", \"تصميم داشبورد بحال هادا\". Not for Dribbble/Behance research (dribbble-design)."
user-invocable: true
argument-hint: "<idea, e.g. \"transport fleet dashboard\"> | <x.com post url>..."
---

# xDesignSkill: design references from X posts

Turns "do a dashboard like the good ones on X" into: a numbered gallery to choose from, the
chosen posts on disk (images, video frames, measured colors), and a design extract a builder
can follow. The reference gives layout, hierarchy, tokens and motion. The product keeps its
own content, brand and data.

Everything runs through one command, `xdesign`, so the steps are the same in every agent.
If `xdesign` is not on the PATH, or the shell refuses the command name, run
`node <folder of this file>/scripts/xdesign.mjs` instead.
It needs Node 18+. `ffmpeg` adds tiles, colors and video frames. Two optional sources make
the search much better: an X login (step 0) and the Grok CLI.

### 0. One time per machine (optional, Mac or any desktop)

```bash
xdesign login     # opens Chrome; the user logs in to X there; `xdesign logout` removes it
xdesign doctor    # shows: grok, x login, web search, pool
```

The session lives in its own Chrome profile at `~/.config/xdesign/chrome-profile` (mode 700),
never in the skill folder. No password is stored: the user types it in the window. Run
`login` only when the user asks for it or agrees, since they must be at the screen. Suggest a
spare X account: automated searching is against X's terms and can get an account flagged.

## Steps

### 1. Ground

- Read the project's design truth, first that exists: `DESIGN.md`, `design/DESIGN-BRIEF.md`,
  a project design-system skill. None: say so; the extract then proposes tokens.
- Note what the reference must be mapped onto: business type, the 5 to 8 numbers or lists the
  main screen has to show, platform (web or mobile), languages (RTL or not).
- Where the harness has a task log (`/kb-spec log`), log the job.

### 2. Find candidates

The user pasted post links and wants exactly those: skip to step 4 with `xdesign download`.

Otherwise turn the ask into one idea string: subject words, sibling words, and the screen type
(`"transport fleet logistics dashboard"`). The screen type (dashboard, mobile, landing) is
what lets a good post about another business still match.

```bash
xdesign find "transport fleet logistics dashboard"
```

It gathers posts from these sources and needs no known accounts. Each one that is not set up
on this machine is skipped with one log line:

1. X's own search, when `xdesign login` was done here: the "Top" and "Latest" results for any
   subject word plus the screen type, UI/UX posts with images or video and 20+ likes.
2. Grok's X search: the `grok` CLI here, else over ssh on `XDESIGN_GROK_SSH` (default
   `MyContabo` when `~/.ssh/config` has it). About 2 to 3 minutes; cached for a day.
3. Web search (DuckDuckGo) for X post links about the idea.
4. The newest posts of the authors those searches turned up.
5. The watchlist (`references/designers.txt` + `~/.config/xdesign/handles.txt`).
6. The pool: every post an earlier run read (`~/.cache/xdesign/pool.json`, newest 2000).

Every link from 1 to 3 is read through the post API before it is shown, so a link Grok made
up, or a deleted post, never reaches the gallery. Posts whose opening text and author handle
name no design work (UI, UX, design, Figma, template...) are dropped, which keeps out news,
crypto and data-course posts that share the words.

When the log says `web search is blocked`, the search engine is rate-limiting this address.
The run still returns pool and watchlist posts. For fresh ones, run the two printed queries
in your own web search tool, collect the `x.com/<handle>/status/<id>` links, and run `find`
again with `--links url,url,...`; their authors are read too.

Ranking: 3 points per subject word, 2 for the same screen type, plus likes and saves, plus
recency. A post that matches only on type is the "close idea, other project type" case; a
well received one can rank above an exact match nobody liked. At most 3 posts per author.

Useful flags: `--days 30`, `--min-likes 50`, `--sort likes|recent`, `--per-author 0`,
`--limit 20`, `--links url,url` (add posts you found with your own web search tool),
`--min-faves N` (X search likes floor, default 20), `--no-x`, `--no-grok`, `--no-web`,
`--no-watchlist`, `--no-pool`, `--all` (keep posts with no word match or no design word).

Output folder: `<project-root>/design/inspiration/<date>-x-<slug>/` (`--out DIR` overrides):
`gallery.html`, `candidates-sheet.jpg`, `candidates.json`, `thumbs/NN.jpg`.

### 3. Let the user choose

- Look at `candidates-sheet.jpg` yourself first (4 per row, number 1 is top left) if you can
  view images. Note the ones that are weak designs or near duplicates.
- Show the user the choice: open `gallery.html` for them (a preview or browser tool, or
  `open`/`xdg-open`), or, in a chat with no way to show a page, list the numbered candidates
  with title, author, likes and link.
- Give your own short recommendation (which 2 or 3, and why), then wait for their numbers.
  Do not pick for them unless they said to; then use `xdesign fetch "<idea>" --top 3`.

### 4. Save the chosen posts

```bash
xdesign pick 3 7 11                    # numbers from the latest gallery of this project
xdesign pick 3 7 --from <folder>       # or name the folder
xdesign download https://x.com/<handle>/status/<id>   # pasted links, no gallery
```

Into the same folder:

- `NN-<handle>-<id>.jpg`: the image at original size.
- `NN-...-t1..t4.jpg`: four overlapping tiles, made when a side is 2600 px or more.
- `NN-...mp4`, `NN-...-fNN.jpg`, `NN-...-sheet.jpg`: the video, 6 to 16 frames spread over its
  length, and one contact sheet of those frames. `.mp4` files are git-ignored.
- `manifest.json`: per post the author, link, date, likes, saves, views and `palette`
  (dominant colors as hex with their share of pixels, sampled from the file, not estimated).
- `README.md`: the same as a table.

`pick` prints the chosen authors that are not on the watchlist. Offer to keep them
(`xdesign handles add <handle>...`), so the next search starts with them.

### 5. Look, in this order

Open the files with your image tool (Claude: Read; Codex: view_image; Gemini and agy: read
the file). An agent that cannot view images says so and stops here; guessing a design from
its caption is not an extract.

1. The whole image or the video sheet: screen list, grid, where the eye goes first.
2. Every tile and the frames that differ: labels, numbers, spacing, radii, icon style, chart
   types, states. Read small text from the tiles, never guess it from the whole image.
3. For a video, compare consecutive frames: what changes, in what order, what stays still.
   That is the motion and interaction model (hover, filter change, drill-down, loading).

Colors come from `manifest.json` `palette`. A color too small to appear there (a thin accent,
a status dot) is written as "accent, about #xxxxxx (by eye)" so the builder knows it was not
measured.

### 6. Write `DESIGN-EXTRACT.md` next to the images

Use `references/extract-template.md`. It has two halves, and the second is the point:

- What the reference does: tokens, layout skeleton, component inventory, charts, motion.
- The same structure filled with this project's content: each reference widget mapped to a
  real number, list or action of the project, or dropped. A healthcare "Bed Occupancy" card
  becomes "Fleet in service" for a transport app; a widget with no counterpart is removed,
  not kept as decoration.

Then decisions `R1..Rn` (adopt / adapt / reject, each with the rule that decides it) and the
hand-off brief. Copy author names and links from `manifest.json`, never from memory and never
from text visible inside an image.

### 7. Hand off

Build from the hand-off brief plus the image paths, with whatever the harness uses for UI
work (Claude: `agy-delegate` or `/frontend-design`, `/enterprise-dashboard`, `/dataviz`,
`/arabic-ui`; other agents: build directly from the extract). Check the result against the
extract (`/unslop`, `/design-check` where present). Close the task log entry.

## Commands

```
xdesign find     "<idea>" [--links url,url] [--handles a,b] [--min-faves N] [--no-x] [--no-grok]
                          [--no-web] [--no-watchlist] [--no-pool]
                          [--days N] [--min-likes N] [--sort score|likes|recent]
                          [--per-author N] [--limit N] [--all] [--out DIR] [--json]
xdesign pick     <n>... [--from DIR] [--no-frames]
xdesign fetch    "<idea>" [find flags] [--top N]
xdesign download <post-url|id>... [--out DIR] [--subject "<text>"] [--no-frames]
xdesign latest   <handle>... [--limit N] [--json]
xdesign handles  [list | add <handle>... | rm <handle>... | check [<handle>...]]
xdesign login | logout
xdesign doctor
```

Exit 3 = nothing matched or nothing to download. `xdesign doctor` checks Node, ffmpeg, the
post API and web search.

## Limits to tell the user about

- Without `xdesign login` and without Grok, posts come only from a web search engine
  (DuckDuckGo), which indexes part of X and lags a few days; the gallery is much thinner.
- X login works only where a window can open (the Mac). Servers get Grok, web and pool.
- That engine blocks an address after roughly 20 requests in a short time. One `find` makes
  2, and repeats of the same idea within a day make none (cached). When blocked, use `--links`.
- Likes and saves measure reception, not design quality. Step 3 exists for that reason.
- The free post API fails at random (404 or an empty list). The script tries three times per
  account and prints `no data`; that is not proof the account is gone. Run again later, do
  not loop.
- Caps per run: 30 post links read, 6 new authors, 30 watchlist accounts, 24 candidates,
  video up to 240 s and 80 MB.

## Rules

- Reference only. Never ship a downloaded file, never reproduce a post one-to-one, never
  reuse its product name, logo, illustrations or copy. Credit stays in `manifest.json`.
- The project's own rules win over the reference: its DESIGN.md tokens, RTL, imagery policy,
  and the owner rule of no purple or violet gradients.
- Low volume, on request only. No cron, no bulk scraping.
- No completion claim without the command output and the folder listing.

## Files

- `scripts/xdesign.mjs` (commands), `lib.mjs` (ranking, parsing), `net.mjs` (post API, web
  search, pool), `xsearch.mjs` (X login and X search, playwright-core installed on first
  `login`), `grok.mjs` (Grok's X search), `media.mjs` (ffmpeg, gallery), `save.mjs` (saving chosen posts; downloads retry, a post with no saved file is not recorded). Tests: `node --test tests/xdesign.test.mjs` from the
  dev-stack root.
- `scripts/link-harnesses.sh`: links this skill into every agent's skills folder on the
  machine and puts `xdesign` on the PATH.
- `references/designers.txt`: seed watchlist. `references/extract-template.md`: extract skeleton.
