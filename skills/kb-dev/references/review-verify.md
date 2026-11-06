# Review and verify rounds (adapted from Ray Amjad task-lifecycle, no Codex)

## Review (fresh reviewer, spec + diff only)
- Diff against the PR's own base branch, not main (stacked PRs).
- Reviewer: via `jdelegate --role reviewer` (`--deep` for high-risk) or `/code-review`. One reviewer per review (owner 2026-11-06): the first model with quota in jdelegate's chain, no second reviewer. Code review: Opus 5.5 at medium. Deep review (auth, money, migrations, security, T4, or `--deep`): Opus 5.5 at high. Arabic-language review: Gemini 4 Argon (`agy/gemini-4-argon-high`). GPT is not in any review chain until a Sol-capable codex plan exists (gpt-5.6-sol is refused on the ChatGPT login); GPT never implements or orchestrates.
- Fix confirmed/must-fix (P1) findings: send to the SAME implementer session. Carry maybes (P2) to the final report.
- A finding that asks for new code must name the path into that state (click, route, API call); otherwise carry it.
- Contradicting reviewers: give the implementer both, it decides. Findings with one root cause get one design.
- The defect is proven; the suggested fix is a guess.
- Max 1 review + 1 fix round; docs-only diffs get no review.
- Reviewer reads `REVIEW.md` at the repo root if present (template: `references/REVIEW.md.template`); it wins over generic checks.
- Tag every finding Important / Nit / Pre-existing. Pre-existing = present before this diff; reported, never blocks.
- The fix round's re-review covers the fix diff only, never re-posts earlier findings, and names the bug CLASS so every instance gets fixed, not one line.
- Learned rules: a finding of the same kind seen twice in a repo becomes a one-line rule in that repo's REVIEW.md (or a lint rule or test), added by the implementer in the fix round.
- Always-owner paths (billing/payments, auth, CI workflows, deploy scripts, DB migrations) need the owner's look even when review is green.

## Verify (fresh verifier, flow matrix only)
- Brief template: `~/code/dev-stack/scripts/gate/verifier-brief-template.md`; preflight runs `~/code/dev-stack/scripts/gate/verify-env-guard.sh <repo>` first and stops on exit 1 if any prod DB/env pattern matches.
- No runnable surface (docs, CI, types, pure refactor): say so and stop.
- Per flow, write the end state the user reaches, rows the app must write, outside side effects, before booting.
- Boot the app against a real non-prod database; fake only the outside services the brief names. Browser for screens, real requests for APIs. Reset DB/state between flows.
- A separate reader checks DB, logs and screenshots for the verdict; route on the verdict, not the driver's claim.
- Evidence per flow: screenshot/recording, or request + response + DB query. Never capture real people's data.
- Outcomes: passed; ran wrong (back to implementer with evidence, max 1 fix round); could not boot (unverified, no fix loop); unreachable (report, ask owner).
