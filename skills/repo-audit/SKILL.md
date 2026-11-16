---
name: repo-audit
description: Supply-chain and safety check for any external GitHub repo, skill, CLI, or MCP server before cloning, running, or installing it. Runs deterministic `repo-audit` first (0 exploration tokens, no untrusted git clone), inspects only flagged files, and returns `SAFE (pin <sha>)` / `RISKY` / `NO`. Triggers on "check this skill", "check this repo", "is this safe to install", "audit this MCP", "/repo-audit", or whenever `install-guard` prompts before installing an unvetted package.
allowed-tools: Bash, Read
---

# Repo Audit (Deterministic Recon + Leaf Judgment)

Never `git clone`, `npx`, `uvx`, or `pip install` an unvetted repository or skill to see what it does. Let `repo-audit` do the reconnaissance deterministically via the GitHub API (or read-only local walk), then apply judgment only to the compact digest.

## Step 1 — Run deterministic reconnaissance (1 command)

```bash
repo-audit "<github-url-or-owner/repo-or-local-path>"
```

`repo-audit` inspects repo provenance, license (`AGPL-3.0`, missing license), pinned 40-char commit SHA, file inventory, `SKILL.md` files, binary blobs, lifecycle hooks (`preinstall`/`postinstall`, `setup.py`, `build.rs`), and red-flag patterns (`curl|sh`, credential paths, API keys, obfuscation, mandatory cloud login gates) in ~2 seconds without executing anything.

## Step 2 — Targeted file read (only if needed)

- If `RISK_LEVEL: LOW` and you only need architectural/utility evaluation, read at most the main `README.md` or `SKILL.md` via `gh api repos/<owner>/<repo>/contents/<path>?ref=<sha> --jq '.content' | base64 -d`.
- If `RED_FLAGS` or `INSTALL_HOOKS` are listed, inspect **only** those exact files at the pinned `<sha>` to separate benign usage (e.g. documentation warning) from real risk.

## Step 3 — Verdict format

Always conclude with one of three verdicts on the first line:

- **`SAFE (pin <owner>/<repo>@<sha>)`** — Permissive license, no hidden install hooks, no credential/network exfiltration, clear utility. Always include the exact 40-char SHA to pin.
- **`RISKY (<short reason>)`** — Usable only in a sandbox or by porting the pattern cleanly (e.g. `deno run -A`, copyleft `AGPL-3.0`, unpinned third-party runtime downloads, or mandatory external account verification).
- **`NO (<hard blocker>)`** — Obfuscated payloads, credential access (`~/.ssh`, `.aws`, API keys), remote shell pipe in install hooks, or zero value over existing `dev-stack` tools.
