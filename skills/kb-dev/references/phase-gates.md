# kb-dev phase gates (moved from SKILL.md 2026-10-27, verbatim)

## Phase 4b: branch before you implement (non-negotiable)

**One spec = one branch = one PR.** The branch name must equal the spec directory name, because `kb-spec` resolves the active feature via `$SPECIFY_FEATURE` → current git branch `NNN-short-name` → *else* highest `NNN` under `specs/`. If the branch does not exist, that resolution silently falls through to the last case and every feature collapses onto whatever branch is checked out — in practice, `main`.

```bash
# specs/012-adw-quality-gates  →  branch 012-adw-quality-gates
git checkout -b "$(basename specs/012-adw-quality-gates)"
```

`/speckit.specify` already does this (`create-new-feature.sh` runs `git checkout -b` and exports `SPECIFY_FEATURE`). When a spec dir is created by hand or by `/kb-spec` without going through `/speckit.specify`, **you must create the branch yourself** before Phase 5.

Enforcement is mechanical, not advisory: `~/.githooks/pre-commit` (global `core.hooksPath`) refuses commits on `main`/`master`/`production`. Merges, rebases, cherry-picks and reverts are allowed, so PRs still land normally. If you genuinely need to bypass it:

```bash
ALLOW_MAIN_COMMIT=1 git commit ...          # once
git config devstack.allowMainCommit true    # this repo, permanently
```

Never reach for the override to route around a missing branch — create the branch instead.

## Phase 8: e2e suites

Phase 8 is the gate for UI changes. Run the suite that matches the app before saying the change works.

- Web: `jev-browse --flows e2e/flows.json` (see `skills/jev/references/e2e-browsing.md`).
- Mobile (Expo/RN; Flutter and native not yet verified for `e2e init`): TesterArmy `e2e`, `npx e2e run --target ios`.
- Evergreen suite: the full mobile flow set, run on every PR by `.eas/workflows/e2e-tests.yml`. Commit `.e2e/cache` so CI replays the verified `act` steps at L0 with no model call.
- Per-PR exploration run: the PR diff and description drive a run that tests the changed features, next to the evergreen suite. Its caching is not documented; assume it pays the model each time until measured.
- On a failure, read `.e2e/artifacts/**/screen.txt` before changing a locator.
- Agent steps: Jev decision executor; text model Haiku 5.5, Arabic screens included; GPT-6 Luna only to judge Arabic wording (see the jev reference).
- Per-PR results go to the PR as a comment via `@e2e-dev/github`.

## Phase 6a: lock the checks before building

The scorer must be untouchable by the builder, or a loop can pass by weakening the tests.

1. Write the checks before the code (Phase 6).
2. Run `lock-checks list <tests>` and show the user each check in plain words. Wait for an explicit OK.
3. `lock-checks approve <tests>` moves them to `tests/locked/` (override with `LOCKED_DIR`), adds an `Edit(...)` deny rule (covers all file-editing tools) to `.claude/settings.json`, commits (rolling everything back if the commit fails), records the approved tree hash in `$(git rev-parse --git-common-dir)/lock-checks/manifest`, and installs a git pre-commit hook in the common git dir (so linked worktrees are covered) that rejects any later commit touching a locked dir.
4. The builder may never edit the locked dir. Loops and workers run `lock-checks verify` after every round; `verify` compares the locked dir against the recorded tree, so committed (even `--no-verify`) and uncommitted tampering both exit 1, which means the round is undone.
5. Only a human runs `lock-checks unlock` (it refuses to overwrite an existing `tests/<sub>`) and commits the result with the human-only env bypass (see `lock-checks -h`). An agent that needs a check changed stops and asks.

## Phase 11 gate: prove the branch and the PR exist

Do not report a feature as finished on assertion. Run these and paste the output — evidence, not claims:

```bash
# 1. Not on a protected branch
BR=$(git rev-parse --abbrev-ref HEAD)
case "$BR" in main|master|production)
  echo "FAIL: still on $BR — the work was never branched"; exit 1 ;;
esac
echo "OK branch: $BR"

# 2. Branch matches the spec dir (one spec = one branch = one PR)
[ -d "specs/$BR" ] && echo "OK spec: specs/$BR" || echo "WARN: no specs/$BR"

# 3. A PR exists for this branch
gh pr view --json url,state --jq '"OK pr: \(.url) [\(.state)]"' \
  || echo "FAIL: no PR — run: gh pr create"

# 4. The spec carries the PR back (loop closed, both directions)
grep -q "^\*\*PR\*\*:" "specs/$BR/spec.md" 2>/dev/null \
  && echo "OK spec stamped with PR" \
  || echo "FAIL: specs/$BR/spec.md has no **PR**: line — run: /kb-spec post"

# 5. Repo can actually receive a PR
git remote get-url origin >/dev/null 2>&1 \
  || echo "BLOCKED: no git remote — no PR is possible until one exists"
```

Before opening the PR also run `scripts/gate/spec-done.sh <repo> specs/<NNN-dir>` and paste its output: it fails on any unchecked `- [ ]` in tasks.md or a missing "Done when" user-flow table. It applies to specs created from 2026-10-27 onward (older specs have no Done-when matrix).

Check 5 is not hypothetical: several local projects (`tokyo`, `up`, `vrcd`, `xavork-saas`, `law`, `software-factory`) have **no remote**, so every PR step silently cannot run there. Report that as blocked rather than claiming success.

For a large change, split it with `gh stack` instead of one giant PR — the `gh-stack` skill is installed.

