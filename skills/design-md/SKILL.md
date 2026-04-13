---
name: design-md
description: Use when the user wants to adopt, reference, or build UI inspired by a real-world brand's design system (e.g. "build this like Linear", "use the Stripe aesthetic", "make it look like Notion", "apply a design system"). Downloads a curated DESIGN.md file into the project root and auto-wires it into the knowledge base. 58+ brands available. Pipeline position — Entry point of the design workflow chain. Upstream: USER. Downstream: design-check (auto-offers conformance scan after brand adoption). Full chain: design-md → design-check → normalize → polish → audit → finishing-a-development-branch.
user-invocable: true
argument-hint: "[brand-name | list]"
allowed-tools: Bash Read Write Skill WebFetch
---

# design-md — adopt a real-world brand design system

Downloads a battle-tested `DESIGN.md` into the project root and auto-wires it into the KB so every future `/frontend-design`, `/normalize`, `/audit`, and `/kb-query` call is automatically grounded in that design system.

**Source:** [awesome-design-md](https://github.com/VoltAgent/awesome-design-md) — served via `npx getdesign@latest add <brand>`.

## Available Brands (58)

```
airbnb      airtable    apple       bmw         cal         claude
clay        clickhouse  cohere      coinbase    composio    cursor
elevenlabs  expo        ferrari     figma       framer      hashicorp
ibm         intercom    kraken      lamborghini linear.app  lovable
minimax     mintlify    miro        mistral.ai  mongodb     notion
nvidia      ollama      opencode.ai pinterest   posthog     raycast
renault     replicate   resend      revolut     runwayml    sanity
semrush     sentry      spacex      spotify     stripe      supabase
superhuman  tesla       together.ai uber        vercel      voltagent
warp        webflow     wise        x.ai        zapier
```

The canonical list lives at `gh api repos/VoltAgent/awesome-design-md/contents/design-md --jq '.[].name'`. Run it if the user asks for a brand not in this static list.

## Steps

### 1. Resolve the brand

- Explicit brand (`/design-md linear.app`) → use as-is.
- Aesthetic description ("dark minimal like Linear", "warm like Claude") → pick the closest match from the list, state your choice in one sentence, then proceed.
- `list`, `?`, or no argument → print the brand table above and ask which one.
- If the brand name is not in the list, run `gh api repos/VoltAgent/awesome-design-md/contents/design-md --jq '.[].name'` to fetch the current list, then retry.

### 2. Find the project root

```bash
# Walk up from cwd to find .git or .claude; fall back to cwd
root=$(cd "$PWD" && while [ "$PWD" != "/" ] && [ "$PWD" != "$HOME" ]; do
  [ -d .git ] || [ -d .claude ] && { echo "$PWD"; break; }
  cd ..
done)
[ -z "$root" ] && root="$PWD"
echo "Project root: $root"
```

**Never** write `DESIGN.md` to `$HOME` or above — if the walk reaches `$HOME` without finding a marker, stop and ask the user to confirm which directory to use.

### 3. Check for existing DESIGN.md

```bash
test -f "$root/DESIGN.md" && echo "EXISTS" || echo "NEW"
```

If `EXISTS`, show the user the first 5 lines of the current file and ask: "A DESIGN.md already exists (looks like `<brand>`). Overwrite with `<new-brand>`? (y/n)". Only proceed on explicit yes.

### 4. Download the DESIGN.md

```bash
cd "$root" && npx --yes getdesign@latest add <brand>
```

The `--yes` flag prevents interactive prompts on first run. Verify the file landed:

```bash
test -f "$root/DESIGN.md" && wc -l "$root/DESIGN.md"
```

Then print the first 10 lines so the user sees what was installed.

### 5. Auto-sync into the KB

Immediately invoke the `kb-docs-sync` skill via the Skill tool — do not wait for the user:

```
Skill tool → skill: "kb-docs-sync"
```

`kb-docs-sync` mirrors all project markdown into `<project-root>/ai-knowledge-base/knowledge/sources/`, so the newly created `DESIGN.md` is automatically indexed. After that, `/kb-query "What are our primary colors?"` returns answers grounded in `[[DESIGN]]`.

**If the KB is not yet initialized** (no `ai-knowledge-base/scripts/query.py` under the project root), invoke `/kb-setup` first via the Skill tool, then retry `/kb-docs-sync`. The user has pre-authorized both bootstraps via the global standing rule in `~/.claude/CLAUDE.md`.

### 6. Brief the user

Read the first 60 lines of `DESIGN.md` and produce a 3-line summary:

1. **Tone:** dark/light, minimal/maximal, editorial/brutalist, etc.
2. **Signature:** one defining color + one defining type choice (pulled from the Color Palette and Typography sections).
3. **Best for:** use cases listed in the file.

Close with exactly: "Design system is active. `/frontend-design`, `/normalize`, and `/audit` will load it automatically. Query it anytime with `/kb-query`."

## Connection to other skills (automatic)

| Skill | How design-md wires in |
|---|---|
| `/frontend-design` | Reads `DESIGN.md` as its first mandatory step — no manual reference needed |
| `/normalize` | Loads `DESIGN.md` as the authoritative design system to align against |
| `/audit` | Checks color contrast, type scale, spacing against `DESIGN.md` tokens |
| `/kb-query` | Answers design-token questions after step 5 auto-sync |
| `/kb-docs-sync` | Invoked automatically in step 5 — mirrors `DESIGN.md` into `knowledge/sources/` |

**No manual wiring required.** Once `design-md` finishes, every downstream skill picks up the DESIGN.md on its next invocation.

## Quick reference

```bash
# Adopt a design system
/design-md stripe

# List all available brands
/design-md list

# Query the active design system
/kb-query "What are the primary colors in our design system?"

# Build UI that matches it
/frontend-design "build a pricing page"
```

## Notes

- **Community-curated, not official.** These DESIGN.md files are reverse-engineered approximations for AI context — ideal for inspiration, not brand compliance.
- **One DESIGN.md at a time.** Running `/design-md` again overwrites the previous file after explicit confirmation.
- **Multiple references?** Copy the old file to `DESIGN-<brand>.md` before overwriting, and reference the named file explicitly in prompts.
- **npx required.** If `npx` is not installed (rare), fall back to fetching from `gh api repos/VoltAgent/awesome-design-md/contents/design-md/<brand>/README.md` and report that the curated version is not directly downloadable.
