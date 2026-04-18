---
name: office-hours
description: Product-level interrogation before you write a single line of code. Walks the user through 6 forcing questions (problem, user, alternatives, value, risks, first milestone) and writes `office-hours/YYYY-MM-DD-<slug>.md`. Triggers on "office hours", "new product idea", "I'm thinking about building X", "product review", "/office-hours". Broader than `brainstorming` — focuses on WHY before HOW. Hands off to `kb-spec pre` → `/speckit.specify` when done.
allowed-tools: Bash Read Write Edit
---

# office-hours — product interrogation before the code

A structured conversation that refuses to move past WHY until the user has clear answers. Not a chat, not brainstorming — a disciplined 6-question walk, with adversarial pressure where the answer is weak.

## When it fires

- "Office hours"
- "I'm thinking about building X"
- "New product / new feature / new service"
- "Let's office-hours this"
- "/office-hours"

Auto-offered at the start of any `/kb-dev` run if no prior spec exists in the KB for the area. Distinguishable from `brainstorming` (which is solution space) because office-hours is problem space.

## The 6 forcing questions

Walk them in order. Do not advance until the current question has a load-bearing answer (at least one concrete user, one concrete pain, one measurable outcome).

### 1. What exact problem?
- Describe the problem in one sentence, no product in it.
- Who feels it? (One named user, not a persona.)
- How often? How bad when it happens?
- What do they do today instead?

Bad answer: "users want better onboarding". Good: "Ahmad signs up, doesn't see his first clinic appointment within 5 min, and churns to WhatsApp messaging."

### 2. Who is this for?
- Name one user. First name, role, context.
- What's their job title, tool stack, budget, decision power?
- Why will they adopt this over their current workaround?

Bad: "SMB founders". Good: "Single-clinic pediatrician in Morocco running paper scheduling, 30-100 appointments/week, has a WhatsApp Business and an iPad."

### 3. What alternatives exist?
- Existing tools (name them).
- DIY workarounds (WhatsApp, Google Sheet, paper).
- Doing nothing.
- What do those cost? What do they get wrong?

If the user can't name 3 alternatives, the problem isn't researched enough — stop.

### 4. What's the measurable value?
- What metric moves? (time saved, revenue gained, error rate dropped)
- By how much? (x2? 10x? 10%?)
- How long before the user notices?

No "it'll be great" answers. Force a number.

### 5. What are the killer risks?
- Technical: what's genuinely hard here?
- Market: who else will build this in 6 months?
- Legal/compliance: HIPAA, GDPR, data residency?
- Operational: who answers support at 2am?

Each risk needs a mitigation or an explicit "we accept this risk".

### 6. What's the first milestone?
- Smallest shippable version that proves the problem is real.
- Time-boxed: 1 week, 2 weeks, max 4 weeks.
- One metric that says "working" vs "not working".

If the milestone takes > 4 weeks, it's not a milestone — it's a project. Re-scope.

## Output

Write `office-hours/YYYY-MM-DD-<slug>.md` at the project root. `<slug>` is derived from question 1's problem statement.

```markdown
# Office Hours: <slug>

**Date:** <ISO>
**Next step:** run `/kb-spec pre "<slug>"` then `/speckit.specify`

## 1. The problem
<one-sentence problem statement, no product in it>

## 2. The user
<named user + context>

## 3. Alternatives
- <alt 1> — cost / limitation
- <alt 2> — cost / limitation
- <alt 3> — cost / limitation

## 4. Measurable value
<metric> moves by <amount> within <time>

## 5. Risks
| Risk | Mitigation |
|---|---|
| <risk 1> | <mitigation or "accepted"> |
| ... | ... |

## 6. First milestone
- Scope: <one-sentence shippable version>
- Time: <≤ 4 weeks>
- Success metric: <one number>

## Open questions
- <things still unresolved — max 3, bring back next office-hours>
```

## Rules

- **No solutioning until question 6.** If the user pitches a feature during question 1, write it down in "Open questions" and return to the problem.
- **Reject "we'll figure it out".** Every question needs at least one concrete answer.
- **Stop at 60 min.** Longer = diminishing returns; schedule another session.
- **Do not write the spec.** Office-hours answers WHY; spec-kit answers WHAT. Hand off.

## Pairs with

- `/kb-spec pre` → `/speckit.specify` — the natural next step after office-hours.
- `grill-me` — if the user says "I'm sure about this", switch to grill-me to stress-test.
- `retro` — office-hours questions inform next-week's bets.
- `brainstorming` — run AFTER office-hours when the WHY is locked and you're exploring the HOW.
