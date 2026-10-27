# Review and verify rounds (adapted from Ray Amjad task-lifecycle, no Codex)

## Review (fresh reviewer, spec + diff only)
- Diff against the PR's own base branch, not main (stacked PRs).
- Reviewer: Opus xhigh via `jdelegate --role reviewer` or `/code-review`; second opinion Gemini 4 Argon only for high-risk diffs.
- Fix confirmed/must-fix (P1) findings: send to the SAME implementer session. Carry maybes (P2) to the final report.
- A finding that asks for new code must name the path into that state (click, route, API call); otherwise carry it.
- Contradicting reviewers: give the implementer both, it decides. Findings with one root cause get one design.
- The defect is proven; the suggested fix is a guess.
- Max 1 review + 1 fix round; docs-only diffs get no review.

## Verify (fresh verifier, flow matrix only)
- No runnable surface (docs, CI, types, pure refactor): say so and stop.
- Per flow, write the end state the user reaches, rows the app must write, outside side effects, before booting.
- Boot the app against a real non-prod database; fake only the outside services the brief names. Browser for screens, real requests for APIs. Reset DB/state between flows.
- A separate reader checks DB, logs and screenshots for the verdict; route on the verdict, not the driver's claim.
- Evidence per flow: screenshot/recording, or request + response + DB query. Never capture real people's data.
- Outcomes: passed; ran wrong (back to implementer with evidence, max 1 fix round); could not boot (unverified, no fix loop); unreachable (report, ask owner).
