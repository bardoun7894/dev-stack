---
source: youtube
url: https://youtu.be/y2ifUC9_zuU
video_id: y2ifUC9_zuU
title: "Vercel's CEO Just Unveiled The Greatest AI Coding Workflow Ever"
channel: AI LABS
date: 2026-10-19
---

# Vercel's CEO workflow, 7 tips (y2ifUC9_zuU)

## Summary

AI LABS distills an interview with Vercel's CEO into seven tips. Core idea: volume of agent work (tokens, changes) says nothing about direction, so check the work against the plan; plus test ideas in a throwaway project, scan for security debt, test as a blind new user, and keep the feedback loop short.

## Key points

- Test ideas in a fresh project from scratch, build an MVP before the full PRD.
- `/direction` command: reads every doc in the specs folder, one agent per doc, a lead agent finds changes not in the plans; output is a drift report, scorecard and action list (keep and update specs, or roll back).
- Security debt grows with agent-written code; run a security scan after each feature.
- Non-negotiables: each rule needs an enforcing check, or it is a wish.
- A destructive "breaker" agent tries to break the app (double submit, odd input, skipped steps).
- Test as a new user who never reads the code; feed real user feedback back in; aim for sessions without errors.

## What we already have

- Security scan: `skills/cso`.
- New-user testing: `dogfood` (never reads the code).
- Error-free sessions: `jev-browse --flows` and `--adversarial`.
- Feedback: Tokyo inbox.

## Gaps

- Drift check against specs: built as `skills/direction` (drift.sh + judge pass, report only).
- Non-negotiables each with a check: `drift.sh` marks HAS-CHECK / NO-CHECK.
- Breaker agent: added as a "Breaker pass" section in `dogfood` (dev/local data only, never prod, no load tests).
