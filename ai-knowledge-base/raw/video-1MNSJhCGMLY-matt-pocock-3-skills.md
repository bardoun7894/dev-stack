---
source: youtube
url: https://youtu.be/1MNSJhCGMLY
video_id: 1MNSJhCGMLY
title: "Matt Pocock's 3 New Skills Close the AI Coding Loop"
channel: Eric Tech
date: 2026-10-20
---

# Matt Pocock's 3 New Skills Close the AI Coding Loop (1MNSJhCGMLY)

## Summary

Walkthrough of three new skills in Matt Pocock's skills repo (v1.3) that close the loop after grooming, to-spec, to-ticket, implement and code review: `implement-spec`, a PR skill, and `retro`.

## Key points

- `implement-spec`: takes the spec and tickets, picks tickets with no open dependencies, runs one agent per ticket in parallel branches, merges them with the code-review skill, then fixes bugs and prepares the PR. TDD and review are built in.
- PR skill: the bottleneck moved from writing code to reviewing PRs. A good PR body has a diagram or pseudo-code of what changed, real test evidence (not an unverified test plan), and a "merge danger" line (one-way vs two-way door, blast radius).
- `retro`: audits a session (or PRs plus sessions) and proposes context fixes and guardrails (automated checks, coding standards) so the same review comment is never written twice.

## What we already have

- implement-spec parallel tickets: `kb-dev` fan-out (phase 5b, NIU threshold) with `dispatching-parallel-agents`.
- PR skill: `~/.agents/skills/pr-pipeline` (L3 brief), `pr-review` bin (L2).
- retro: `skills/retro` (session mode and weekly mode).

## Gaps

- kb-dev does not yet point at pr-pipeline L3 (evidence, merge danger, diagram) when it opens a PR. Wired in kb-dev phase 9/11.
- No scheduled trigger for `retro session`. Wired in kb-dev as weekly / after a long run, human picks fixes.
