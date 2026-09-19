<!-- BEGIN jev-first (dev-stack skills/jev/references/jev-first-rule.md) -->
## Jev first: System 1 before any model

Before calling a model, spawning an agent, or reading many items only to sort them, ask whether Jev can
answer. If the output is a label, yes/no, probability, score, routing target or model tier, use the `jev` CLI
(`jev choice / noul / score / route`, ~$0.00002 and under a second). Jev is System 1: it screens every item and
picks every step. You are System 2: you write text and code, handle what Jev escalates, and retune its
questions. An LLM only runs when there is text or code to produce, an image to read, input over 32k tokens,
or Jev is below its confidence bar / errors (exit 2 or 3). Fall back then; never treat that as a pass.

Tools on PATH (Mac `~/.local/bin`, MyContabo `/usr/local/bin`):
- `jev route "<task>" -q`: which model tier a task needs (T0 = no model, just `jev`).
- `jev-review diff [BASE]`: screen every hunk before a review; its `route:` line says none / reviewer / codex / panel.
- `jev-review lint [PATH…]`: secrets or PII in logs, names hiding side effects, useless comments (exit 1 on errors).
- `jev-review scan [DIR] [--run]`: code smells and garbage comments, cost estimate first.
- `jev-browse --flows flows.json` / `--adversarial N`: Jev drives the browser (Lightpanda) and judges each flow.
- `jev … --log TAG`, then `jev tune TAG`: review Jev's decisions and revise its criteria and thresholds.

Full guide: the `jev` skill (`SKILL.md`, `references/e2e-browsing.md`).
<!-- END jev-first -->
