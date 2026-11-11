---
name: boat
description: Control boat.dev cloud sandboxes (persistent Ubuntu VMs) and the boat GitHub Actions runner. Use for "boat", "boat.dev", "run tests on boat", "sandbox VM", "runs-on: boat", "CI on boat", "instead of MyContabo for tests", isolated test runs, PR CI.
---

# boat

Helper: `python3 ~/.claude/skills/boat/scripts/boat.py` (stdlib only, all subcommands take `--json`).
API contract: `references/api.md`.

## When to use boat vs MyContabo

- boat: PR CI, and isolated one-off test runs (`run`) that must not touch the dev server.
- MyContabo (`gate-run` / `gate-submit`): dev servers, herdr workers, deploys, anything long-lived.

## Hard rules

1. MEDIA TGB (bardoun7894/mediatgb) CI runs on boat (owner 2026-11-11, replaces the 2026-11-02 no-boat rule): repo variable `CI_RUNS_ON` = `"boat"`, `CI_CONTAINER` unset. Full CI took 10 min on boat vs ~53 min median on the laptop runner. Fallback: `CI_RUNS_ON` = `["self-hosted","cachy"]` and restore `CI_CONTAINER` (laptop image `localhost:5000/mediatgb-ci:2`).
2. Always delete sandboxes. `stop` keeps a BILLED snapshot; use `stop` only when you truly need to resume.
3. The API key lives in env `BOAT_API_KEY` or `~/.config/boat/key` (chmod 600). Never put it in briefs, logs, commits or command lines.
4. boat VMs have network access, unlike the factory's `--network none` Docker sandbox. Do not run untrusted code with secrets present.
5. EU regions only (Germany, Finland, France), not selectable.
6. Do not install the boat CLI or pipe install scripts to a shell; use this script.

## Commands

```
boat.py ls
boat.py new [--size small|default|large|xlarge] [--ttl 3600]
boat.py status ID
boat.py exec ID [--timeout S] -- CMD       # >600 s auto-switches to detached+poll; exits with CMD's code
boat.py push ID DIR                         # git ls-files only -> ~/workspace/<dirname>
boat.py run [--push DIR] [--size small] -- CMD   # create, push, run, ALWAYS delete
boat.py stop ID | delete ID
boat.py cleanup [--older-than HOURS] [--yes]     # dry run unless --yes
boat.py ci enable REPO_PATH [--workflow FILE]    # ubuntu-latest -> boat, shows diff, no commit
boat.py ci status OWNER/REPO                     # gh run list summary
```

Put options before `--`; everything after it is the remote command.

## Typical flows

- Tests: `boat.py run --push . --size small -- 'npm ci && npm test'`. Exit code equals the test exit code. Commands run in `~/workspace/<dirname>`.
- CI: `ci enable ./repo`, review the diff, commit and push yourself. One-time: link GitHub (`POST /ci/connect`, dashboard CI tab) and store a `ci` preset key as the repo secret. Size labels: `boat-small`, `boat`, `boat-large`.
- Leftovers: `cleanup --older-than 2` to preview, add `--yes` to delete. Check `ls` after any failed run.

## Limits

- Sync command max 600 s; `exec` handles longer via detached. Job max 6 h on CI.
- Default ttl 3600 s auto-stops the VM (this stop leaves a billed snapshot); `run` deletes anyway.
- `ci status` needs an authenticated `gh`.
