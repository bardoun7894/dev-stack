---
name: grill-me
description: Adversarial planning interviewer. STANDALONE — only fires on explicit invocation ("grill me", "stress-test this", "poke holes", "convince me", "what am I missing"). Walks a structured 7-phase decision tree and writes decisions.md. Never auto-fires from kb-dev, brainstorming, or any workflow. Pipeline position — Parallel to kb-dev phase 1 (brainstorming) but opt-in only. Upstream: USER only. Downstream: writing-plans (if the user accepts the adversarial findings as planning input).
allowed-tools: Bash Read Write Edit Glob Grep
---

# grill-me — adversarial planning interviewer

A planning-mode skill that interviews the user **relentlessly but structurally** until every important decision is resolved. It is not a chatty back-and-forth — it is a disciplined walk down a coverage tree, with adversarial pressure on each node, ending in a written record.

## When to fire

**Only on explicit user invocation.** This skill is intentionally separated from the `kb-dev` pipeline — it is opt-in, not automatic.

Trigger phrases (EN):
- "grill me" / "/grill-me"
- "stress-test this"
- "poke holes"
- "convince me this is right"
- "what am I missing"
- "interrogate this plan"

Trigger phrases (AR):
- "اختبرني" / "اسألني"
- "ضع تحت الضغط" / "اختبر هذا"
- "ابحث عن الثغرات"
- "أقنعني أن هذا صحيح"
- "ماذا فاتني"
- "استجوب هذه الخطة"

Do **not** fire automatically from `kb-dev`, `brainstorming`, `kb-spec`, or any other workflow skill. The user calls grill-me when they decide they want it, and never otherwise.

## The seven phases

### Phase 1 — Recon (silent, before asking anything)

Before the first question, gather context so questions are sharp and non-redundant:

1. Run `/kb-query "<topic> prior decisions architecture constraints"` — the KB knows what was decided before. Cite the wikilinks back to the user when challenging their plan.
2. `Glob` for related files (`spec.md`, `plan.md`, `tasks.md`, `*.test.*`) to know what already exists.
3. Read 1–3 most relevant existing files to understand the current shape.
4. If `specs/<feature>/decisions.md` already exists from a prior grill-me run, read it — do not re-ask resolved questions.

Output of recon (internal): a list of known facts, a list of suspected gaps, and a list of contradictions between what the user said and what the KB says.

### Phase 2 — Coverage tree

Walk the user through these eight categories, **in order**, in this priority. Each category has 2–6 questions; ask them one at a time. Skip categories that are genuinely irrelevant, but say so out loud ("Skipping security category — this is a pure-frontend animation").

| #  | Category               | Sample questions                                                                                  |
|----|------------------------|---------------------------------------------------------------------------------------------------|
| 1  | **Functional scope**   | What is the smallest version that ships? What is explicitly out of scope? Who is the user?        |
| 2  | **Data model**         | What is the schema? What invariants must hold? What gets persisted vs computed vs cached?         |
| 3  | **Failure modes**      | What happens if the network drops mid-write? If the worker dies? If two clients race?            |
| 4  | **Edge cases**         | Empty state. Single item. 10k items. Unicode. Timezone boundaries. Negative numbers. Permissions. |
| 5  | **Security & privacy** | Auth boundary. Rate limits. PII handling. Tenant isolation. Trust boundary at every input.        |
| 6  | **Performance & scale**| Expected QPS. p50 / p99 latency budget. Memory budget. What gets indexed.                         |
| 7  | **Operability**        | How is it deployed? Rolled back? Observed? What logs / metrics / alerts? Migration path.          |
| 8  | **Test plan**          | What is the smallest failing test? What are the integration boundaries? What cannot be tested?   |

For each question:
- **Ask one at a time.** Never batch.
- **Provide your recommended answer first** based on recon, then ask "agree / disagree / adjust".
- **If the user hand-waves, push back once.** "What does 'handle errors gracefully' mean here? Pick a specific behavior: retry, fallback, fail loud, or silently drop?"
- **Cite the KB when relevant.** "The KB says we standardized on `lockForUpdate` for token assignment in [[booking-flow]] — does this feature need the same?"

### Phase 3 — Adversarial pressure

For every answer the user commits to, generate **one strong counter-argument** in the role of an experienced reviewer:

- "Counter: that approach broke last time in [[duplicate-booking-prevention]]. What is different now?"
- "Counter: this design assumes the client retries idempotently. What guarantees that?"
- "Counter: this introduces a new dependency. What happens when it goes down?"

The user must address the counter — either accept the change, document why the original answer still holds, or mark the question as a known risk.

### Phase 4 — Dependency resolution

Some answers depend on others. After phase 3, walk the decision graph and surface **dependent questions** the user has not yet seen:

- "You said writes go through a queue (Q3) and that operators can edit records (Q5.2). What happens when an operator edit lands while a queued write is in flight? You haven't answered that yet."
- "You chose Postgres (Q2.1) and said this must work offline (Q1.4). Those conflict — pick one or describe the sync mechanism."

Keep doing this until no new dependent questions surface.

### Phase 5 — Risk scoring

For every decision, assign a severity:

- **P0** — wrong answer ships a broken product. Must be resolved.
- **P1** — wrong answer causes a measurable regression. Should be resolved.
- **P2** — defensible either way; document the choice.
- **P3** — bikeshed; decide quickly and move on.

Only P0s block phase 6.

### Phase 6 — Write the decisions document

Write `specs/<feature>/decisions.md` (or `decisions.md` in cwd if no spec dir) with this exact structure:

```markdown
# Decisions — <feature name>

**Date:** <YYYY-MM-DD>
**Grilled by:** grill-me
**Status:** draft | locked

## Resolved (P0)
- **Q:** …
  **A:** …
  **Why:** …
  **Counter considered:** …
  **KB refs:** [[…]], [[…]]

## Resolved (P1, P2)
…

## Open risks (deferred)
- …

## Out of scope
- …
```

Then run `/kb-docs-sync` so the decisions doc gets mirrored into the KB and shows up in future `/kb-query` runs.

### Phase 7 — Time check & exit

Grill sessions can drift. After every 10 questions:

- Tell the user how many P0s remain unresolved.
- Offer the choice: "Continue grilling, pause and write the decisions.md as-is, or hand off to /kb-spec pre with what we have."

Hard cap: 30 questions per session unless the user says "keep going". Beyond 30, write the decisions.md, mark unresolved P0s as "DEFERRED — needs follow-up", and exit.

## Operating principles

1. **One question at a time.** Never batch. Batched questions get batched non-answers.
2. **Recommend first, ask second.** Saying "I think X because Y — agree?" is faster than "what do you think?".
3. **Codebase beats user.** If the question is answerable by reading the codebase, read it. Do not waste the user's time.
4. **KB beats codebase.** If the question was decided in a prior session, cite the KB and move on.
5. **No performative questioning.** If you already know the answer with high confidence, state it and ask the user to confirm — do not pretend ignorance.
6. **Adversarial, not hostile.** The point is to find weaknesses, not to score points. Frame counters as "here's how this could fail" not "you're wrong".
7. **Always end in writing.** A grill session that does not produce `decisions.md` was wasted — context disappears, and the next session starts from zero.

## Integration with the rest of the suite

- **Upstream:** Runs after `brainstorming` (obra) when the user is committed to a direction but the design is fuzzy. Or runs cold when the user explicitly asks.
- **Downstream:** Hands off to `/kb-spec pre` → `/speckit.specify`. The spec authoring is now grounded in `decisions.md`, so the spec phase becomes mostly transcription instead of debate.
- **Sister skill:** `writing-plans` (obra) — grill-me resolves the *what*; writing-plans resolves the *how*. Run grill-me first.
- **Inverse skill:** If the user is truly exploring (no committed direction yet), use `brainstorming` instead — that one is divergent, this one is convergent.
