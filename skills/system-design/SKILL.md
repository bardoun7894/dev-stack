---
name: system-design
description: Write specs/NNN/system-design.md before a new app/project is built (after spec.md + research.md, before /kb-spec plan + /speckit.plan), then hard-stop for owner approval of the D-codes and Q-codes. Triggers on "system design", "design the system", "architecture before we build", "/system-design", and Arabic "تصميم النظام", "معمارية النظام", "صمم النظام قبل البناء". Runs only for new apps/projects (owner rule 2026-10-21); never for features in an existing app, even ones adding a service or datastore.
allowed-tools: Bash Read Write Edit Glob Grep Skill
---

# system-design — architecture decisions before the plan

Sits in kb-dev as phase 2c: after `spec.md` + `research.md`, before
`/kb-spec plan`. Output is `specs/NNN/system-design.md`. Ends in a hard stop:
nothing is planned or built until the owner approves.

It does not redo product or UX design (brainstorming did that) and does not
duplicate plan.md's "Technical Context" / "Project Structure" or Spec Kit's
field-level `data-model.md`. It fixes the system-level choices the plan then
cites.

## Triggers

- `system design`, `design the system`, `architecture before we build`, `/system-design`
- Arabic: `تصميم النظام`, `معمارية النظام`, `صمم النظام قبل البناء`

## When to run

- Every NEW project (owner rule: new project = folder + kb-dev + specs).
- Skip: every feature or change inside an existing app (owner rule 2026-10-21).

## Pick the size

| Size | Use when | Required sections |
|------|----------|-------------------|
| LITE | single app, one host, no new infra, no new external provider | 1, 2, 4, 6, 9, 10 |
| FULL | anything else: second host, queue, new datastore, new provider, multi-tenant, media/AI pipeline, client data | 1-10 |

Unsure: FULL. Say which size you picked and why in the first line of the file.

## Steps

1. **Read inputs**: `specs/NNN/spec.md`, `research.md`, and the `/kb-query` result for the project domain.
2. **Inventory reuse** before proposing anything new. What the owner's stack already runs:
   - MyContabo server-first websites (`/root/<name>`, pm2 or Docker)
   - shared Temporal at `100.64.0.1:7233` (workflows, retries, schedules)
   - Laravel / Next.js app stacks
   - Kie.ai for media generation, OpenRouter for LLMs
   - Jev for labels and routing
   Prefer reuse. Every new piece of infra needs a D-code that says why reuse failed.
3. **Fill** `references/template.md` into `specs/NNN/system-design.md`. Numbers are real or `unknown -> Qn`; never invented. No TBD/TODO.
4. **One second opinion**, load-bearing decisions only (hosting, datastore, sync vs async, tenancy):
   `fusion --mode json -p '/opinion <question>' </dev/null`
   Run it once, not in a loop. Record the verdict under the affected D-code.
5. **Gate**: `bash ~/.claude/skills/system-design/scripts/check.sh specs/NNN/system-design.md --lite|--full`
   and walk `references/checklist.md`. Fix and re-run until exit 0.
6. **HARD STOP.** Show the owner the D-codes (decisions, with the recommended option) and the Q-codes (open questions). Wait for explicit approval. Answers to Q-codes go back into the file as decisions. Do not start step 7 on silence.
7. After approval: `/kb-spec plan` then `/speckit.plan`. plan.md's Technical Context cites `system-design.md` (by D-code) instead of repeating it. Store the approved decisions with `/kb-ingest`.

## Hosting rules to apply in section 2

- Contabo's GTC forbids serving Syrian users: such projects go to Hetzner, not MyContabo.
- MyContabo has limited RAM: one builder at a time; say so in the deploy section.

## Files

- `references/template.md` - the 10 sections
- `references/checklist.md` - reviewer checklist used before the stop
- `scripts/check.sh` - zero-AI structure gate (headings, mermaid, D1, no placeholders)
- `tests/sample-full.md`, `tests/empty.md` - gate fixtures (pass / fail)

## Non-goals

- Product scope, personas, UX flows: brainstorming / spec.md.
- Library choices and file tree: plan.md.
- Field-level schemas: Spec Kit data-model.
