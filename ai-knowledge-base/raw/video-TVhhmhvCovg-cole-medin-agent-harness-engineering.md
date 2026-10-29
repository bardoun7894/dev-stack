---
source: youtube
url: https://youtu.be/TVhhmhvCovg
video_id: TVhhmhvCovg
title: "Let Your AI Agent Do ITS OWN Harness Engineering"
channel: Cole Medin
date: 2026-10-20
---

# Let Your AI Agent Do ITS OWN Harness Engineering (TVhhmhvCovg)

## Summary

Harness engineering (rules, skills, subagents, hooks, memory) applies to production agents as much as to coding agents, since both are Markdown-defined. Two loops improve a production agent: a memory loop and a retro loop over traces. Demo on LangChain managed deep agents: 4 of 14 questions right at first, 13 of 14 after both loops.

## Key points

- Memory loop: when the agent is unsure it escalates to an inbox; the human's answer is stored as a case-by-case lesson the agent can look up.
- Retro loop: an engine reads production traces, describes each error, links the trace, and proposes a concise change to instructions/skills. A human approves; changes are versioned and can be rolled back.
- The human stays in the loop: the agent finds and proposes fixes, never silently rewrites its own harness.
- Keep proposed rule changes short so the rules file does not bloat.

## What we already have

- Dev side: `skills/retro` (proposes ranked fixes, human picks, never auto-applies) and `skills/self-tune`.

## Gaps

- Dev side: none beyond wiring retro into kb-dev (weekly / after a long run).

## For Tokyo/crmAi later

Note only, nothing built:
- Escalation inbox: when the bot is unsure, route the question to the owner; the answer becomes a stored lesson looked up later.
- Retro over conversation traces: periodic job that reads bot conversations, finds mistakes, proposes short rule edits; owner approves each one.
- Version the bot's instructions so a bad change can be rolled back.
