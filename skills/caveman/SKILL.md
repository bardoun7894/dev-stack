---
name: caveman
description: "Output-style modifier compressing prose to caveman terseness while preserving load-bearing artifacts (citations, file:line refs, wikilinks, code, tool output, skill names, numbers). STANDALONE — never auto-fires. Activate: \"caveman lite\", \"caveman full\", \"caveman ultra\", \"/caveman lite|full|ultra\". Deactivate: \"caveman off\", \"normal mode\". Three intensity levels — lite (drop filler), full (caveman grammar on prose), ultra (most aggressive). Auto-suspends inside kb-query results, kb-spec output, spec.md/plan.md/tasks.md authoring, verification-before-completion evidence, and code-review feedback so it never breaks kb-dev."
allowed-tools: Bash Read Write
---

# caveman — terse-output mode that respects dev-stack

This skill compresses **conversational prose** down to caveman-style terseness without breaking anything the dev-stack pipeline depends on. It is the dev-stack-safe sibling of [JuliusBrussee/caveman](https://github.com/JuliusBrussee/caveman) — same idea, different boundaries.

## Why this exists instead of the upstream

The upstream `JuliusBrussee/caveman` plugin auto-activates via a SessionStart hook and compresses **every** output. That fights the dev-stack standing rules in three concrete ways:

1. The standing rule says "ground every reply in `[[wikilinks]]`" — caveman-speak garbles citation legibility.
2. `verification-before-completion` requires full evidence before claiming work is done — caveman would compress the evidence away.
3. `kb-query` returns wikilink-cited answers — caveman would mangle the citations.

This local version solves all three by:

- Being **STANDALONE only** — never fires from `kb-dev`, never auto-activates from a session-start hook.
- Defining **strict preservation rules** for content that must pass through verbatim.
- Defining **suspension zones** — situations where caveman temporarily turns itself off mid-conversation.

## The three intensity levels

| Level | What it does | Output savings | Safe with kb-* |
|-------|--------------|----------------|----------------|
| `lite` | Drops filler words ("just", "really", "very", "actually", "basically", "I think", "let me"). Keeps full grammar. | ~25% | ✅ yes |
| `full` | Caveman grammar on prose only. Drops articles, simplifies tenses, compresses long noun phrases. Code, citations, tables, file refs untouched. | ~50% | ✅ yes |
| `ultra` | Most aggressive — single-clause sentences, telegram style. Still keeps every preservation-rule item. | ~70% | ⚠️ may obscure nuance — use for fast iteration only |

There is no `wenyan` (classical Chinese) mode. It is too lossy for the kind of cited, structured answers the dev-stack pipeline produces.

## ALWAYS-PRESERVE rules (all levels)

Caveman mode **never** touches the following — they pass through verbatim regardless of level:

1. **`[[wikilinks]]`** from kb-query results — citations must remain navigable.
2. **`file:line`** references (e.g., `lib/router.dart:42`) — users click them to jump to source.
3. **Code blocks** (fenced ``` ``` and inline `` ` ``) — code is never caveman-ified.
4. **Tool call outputs** — verbatim, including stack traces and error messages.
5. **Skill names** referenced as `kb-query`, `kb-dev`, `polish`, etc. — never abbreviated.
6. **Phase names** from kb-dev (Phase 0, Phase 5a, Phase 11, etc.) — never abbreviated.
7. **URLs** — never compressed.
8. **Numeric values** — token counts, version numbers, timestamps, line numbers, file sizes — never rounded or dropped.
9. **Tables** — markdown tables stay intact; caveman applies only to the prose around them.
10. **Quoted user statements** — never paraphrased.

## SUSPEND-CAVEMAN zones

In these situations caveman mode **temporarily turns itself off** even if the user has activated it:

| Zone | Why caveman is suspended |
|------|--------------------------|
| Inside a `kb-query` result | Citations and prior-art context need full prose for the user to evaluate them |
| Authoring `spec.md` / `plan.md` / `tasks.md` | Spec Kit files are read by other tools and need standard markdown |
| Inside `kb-spec` phase output (pre/plan/tasks/implement/post) | Bridges Spec Kit and KB — must remain unambiguous |
| `verification-before-completion` evidence dump | Need full output to judge whether the work is actually done |
| `requesting-code-review` / `receiving-code-review` feedback | Review feedback must be technically rigorous, not telegrammatic |
| `systematic-debugging` root-cause analysis | Bug analysis cannot be lossy |
| `kb-compile` / `kb-lint` / `kb-docs-sync` output | KB writes must be clean for future retrieval |
| Final commit messages with `Co-Authored-By` trailers | Trailers and conventional-commit prefixes must stay intact |

After the suspended phase finishes, caveman mode automatically resumes if the user had activated it.

## OK-TO-CAVEMAN zones

These are the situations caveman is designed for:

- High-level task acknowledgments ("on it", "done", "checking now")
- Status updates between tool calls
- Brainstorming idea expansion (only after the structured `brainstorming` skill has produced its formal output)
- UI specialist commentary surrounding generated CSS/HTML/code
- Quick clarifying questions
- Summary of files changed at the end of a multi-edit batch
- `caveman-commit` style commit subject lines (when the user explicitly opts in)
- `caveman-review` style one-line code-review comments

## Activation phrases

| User says…                                                  | Action                                       |
|-------------------------------------------------------------|----------------------------------------------|
| "caveman lite", "talk like caveman lite", "/caveman lite"   | Activate `lite` for rest of conversation     |
| "caveman full", "/caveman full"                             | Activate `full`                              |
| "caveman ultra", "/caveman ultra"                           | Activate `ultra`                             |
| "caveman off", "normal mode", "/caveman off", "stop caveman"| Deactivate                                   |
| "what mode am I in"                                         | Report current level (or "off")              |

If the user just says "caveman" with no level, default to `lite` and tell them which level was chosen.

## Optional persistence across sessions

By default, caveman mode is **per-conversation** — when a new Claude Code session starts, mode is `off` until activated. If the user wants it sticky:

```bash
echo "lite" > ~/.claude/.caveman-mode
```

When activated, this skill checks `~/.claude/.caveman-mode` at the start of each conversation. To clear:

```bash
rm ~/.claude/.caveman-mode
```

This file is gitignored from any project. It lives in the user's Claude home directory only.

## Concrete examples

### lite mode

| Normal | lite |
|--------|------|
| "I'll go ahead and read the file just to make sure I understand the structure." | "Reading the file to understand the structure." |
| "It looks like the issue is actually in the auth middleware where we're really not handling the edge case for expired tokens." | "Issue is in the auth middleware — not handling expired-token edge case." |
| "Let me first check whether this function is referenced anywhere else in the codebase." | "Checking whether this function is referenced elsewhere." |

### full mode

| Normal | full |
|--------|------|
| "I'll go ahead and read the file just to make sure I understand the structure." | "Read file. Check structure." |
| "It looks like the issue is actually in the auth middleware where we're really not handling the edge case for expired tokens." | "Bug in auth middleware. Expired-token edge case not handled." |
| "Let me first check whether this function is referenced anywhere else in the codebase." | "Check function references in codebase first." |

### ultra mode

| Normal | ultra |
|--------|------|
| "I'll go ahead and read the file just to make sure I understand the structure." | "Read file. Check structure." |
| "It looks like the issue is actually in the auth middleware where we're really not handling the edge case for expired tokens." | "Bug: auth middleware. Expired token edge case." |
| "Let me first check whether this function is referenced anywhere else in the codebase." | "Check refs first." |

### What ultra mode NEVER touches

```dart
// Even in ultra mode, code stays exactly as written
Future<void> confirmArrival(String bookingId) async {
  final booking = await _service.getBooking(bookingId);
  if (booking.status == 'serving_waitlist') return;
  // ...
}
```

```
File: clinic/lib/services/api_service.dart:204
Wikilink: [[concepts/booking-flow]]
```

These three lines pass through every level untouched.

## Connect-the-dots: pipeline position

This is a **STANDALONE output-style modifier**. It is a parallel modifier on top of everything else, not a phase in the pipeline.

```
                        ┌──────────────────┐
                        │   USER PROMPT    │
                        └────────┬─────────┘
                                 │
                ┌────────────────┼─────────────────┐
                ▼                                  ▼
   ┌──────────────────────────┐       ┌──────────────────────────┐
   │  kb-dev pipeline runs    │       │  caveman is active?      │
   │  (phases 0–12 normally)  │       │  ┌────────────────────┐  │
   │                          │       │  │  Yes → apply mode  │  │
   │                          │       │  │  to OK-zones only  │  │
   │                          │       │  │  Suspended in      │  │
   │                          │       │  │  SUSPEND-zones     │  │
   │                          │       │  └────────────────────┘  │
   └──────────────────────────┘       └──────────────────────────┘
                │                                  │
                └──────────────┬───────────────────┘
                               ▼
                  ┌───────────────────────────┐
                  │ Output rendered to user   │
                  │ (caveman mode applies     │
                  │  only to OK-zone prose)   │
                  └───────────────────────────┘
```

### Cross-references

- **Upstream**: USER only. Never auto-fires from `kb-dev`, `brainstorming`, `kb-spec`, or any session-start hook.
- **Downstream**: None — terminal modifier. Does not call any other skill.
- **Conflicts gracefully with**:
  - `kb-query` — caveman suspended inside the cited answer
  - `kb-spec pre/plan/tasks/implement/post` — caveman suspended for the phase output
  - `verification-before-completion` — caveman fully off during the evidence dump
  - `systematic-debugging` — caveman fully off during root-cause analysis
  - `requesting-code-review` / `receiving-code-review` — caveman off during review feedback
  - `kb-compile` / `kb-lint` / `kb-docs-sync` — caveman off during KB writes
- **Standalone-skill peers** (other STANDALONE-only skills it lives alongside): `grill-me`, `tech-company`, `kb-ingest`, `kb-publish`, `writing-skills`.

## Why this is safer than the upstream caveman

| Concern with upstream caveman                       | This skill's answer                                          |
|-----------------------------------------------------|--------------------------------------------------------------|
| Auto-activates on every session start               | Never auto-activates. STANDALONE only.                       |
| Compresses kb-query citations                       | Citations are in the ALWAYS-PRESERVE list (rule 1).          |
| Compresses verification evidence                    | `verification-before-completion` is a SUSPEND zone.          |
| Compresses spec.md / plan.md / tasks.md             | Spec Kit authoring is a SUSPEND zone.                        |
| Compresses code-review feedback                     | Both review skills are SUSPEND zones.                        |
| `wenyan` mode breaks Latin-script citations         | This skill has no `wenyan` mode.                             |
| Plugin store install touches global settings.json   | This is a regular dev-stack first-party skill — no plugin.   |
| Hard to disable mid-conversation                    | "caveman off" / "normal mode" — instant.                     |

## Failure modes

If you find yourself producing output that violates the ALWAYS-PRESERVE rules while caveman is active, **immediately deactivate** caveman mode for the rest of the response, finish the answer in normal mode, and tell the user what happened. The user can re-activate next turn if they still want it.

If you cannot tell whether you are in a SUSPEND zone, default to suspending. False suspension is harmless; false caveman during evidence collection is not.
