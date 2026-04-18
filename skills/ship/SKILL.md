---
name: ship
description: Deploy a verified-green branch to its detected target (Docker/Vercel/Firebase/k3s/GitHub Actions). Triggers on "ship this", "deploy to prod", "release this", "push to production", "/ship". Auto-offered after `finishing-a-development-branch` closes the PR. Refuses if tests have not passed or PR is still open with failing CI. Delegated to by DevOps role; never skips QA sign-off.
allowed-tools: Bash Read Grep
---

# ship — one-command deploy

The last mile. Detects the deploy target, runs it, confirms it, reports back.

## Preconditions (hard-fail if any miss)

1. **Tests pass on current HEAD.** Run project's test command; stop if any fail.
2. **Clean working tree.** `git status --porcelain` empty. No uncommitted work.
3. **CI green on the branch.** `gh pr checks --watch=false` returns no failures.
4. **On deployable branch.** `main` / `master` / `production`, or a branch with a merged PR. Refuse on feature branches without a merged PR.

Any failure → report it and stop. Do not deploy.

## Detect deploy target

Walk the project root for markers, first-match wins:

| Marker | Target | Command |
|---|---|---|
| `docker-compose.yml` (prod profile) | Docker Compose | `docker-compose up -d --build` |
| `Dockerfile` + `k8s/` or `k3s/` | Kubernetes | `kubectl apply -f k8s/` or `kubectl rollout restart` |
| `vercel.json` | Vercel | `vercel --prod` |
| `firebase.json` | Firebase | `firebase deploy` |
| `.github/workflows/deploy.yml` | GitHub Actions | `gh workflow run deploy.yml --ref main` |
| `fly.toml` | Fly.io | `fly deploy` |
| `netlify.toml` | Netlify | `netlify deploy --prod` |
| `Procfile` + `heroku` remote | Heroku | `git push heroku main` |

If multiple markers match, ask the user which. If none, ask the user to configure the target (don't guess).

## Execute

1. Print the detected target + exact command.
2. Ask one confirmation: "Deploy to <target> with `<command>`? [y/N]". Require `y`.
3. Run the command, stream output.
4. On failure: stop, report stderr, suggest `/investigate` or rollback per target.
5. On success: verify with a health check if the project has one (GET `/_health`, `/api/health`, or the URL printed by the deploy tool). 3 retries, 2s apart.

## Report

```
Deployed: <target>
Command:  <command>
Duration: Xs
Health:   200 OK <url> (or "no health check configured")
Commit:   <sha>  <subject>
PR:       <url if any>
Next:
  - /canary to monitor the first minutes
  - /document-release to auto-generate release notes
  - /retro at end of week
```

## Rules

- **Never deploy feature branches** — only `main`/`master`/`production` or branches with merged PRs.
- **Never skip the health check** when one is configured.
- **Never deploy without confirmation** unless `--yes` is explicitly passed and the standing rule permits (it currently does not).
- **Always report the sha** so rollback is trivial.

## Pairs with

- `finishing-a-development-branch` — auto-offers `/ship` as the last step after merge.
- `canary` — run after `ship` to watch the first minutes.
- `document-release` — auto-generate release notes from the commit range.
- `retro` — weekly summary of what shipped.

## Failure recovery

If deploy fails mid-way:
- Docker: the previous container is still running; `docker ps` to confirm.
- Vercel/Netlify/Fly: they're atomic — failed deploys don't replace prod.
- Kubernetes: `kubectl rollout undo deployment/<name>`.
- Heroku: `heroku releases:rollback`.
- GitHub Actions: check the workflow run; rerun with `gh run rerun`.

Report the rollback command to the user; don't execute without explicit approval.
