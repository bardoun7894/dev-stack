# gate kit: zero-AI project gate

Loops, queues and watchers live in bash. The AI acts only on a result (PASS / FAIL / STALL).

## Set up
1. Write `<repo-root>/.gate.conf` (bash-sourceable; do not commit secrets). Example: `projects/board/.gate.conf`.
2. Work in git worktrees under `<repo-root>/.worktrees/<dir>`.
3. State lives in `~/.cache/gate/<repo-name>/`: `gateq.txt`, `gate-<n>.log`, `gate-<n>.done`, `full-<n>.txt`, `.seen-*`.

## Scripts (this dir)
- `gate.sh <worktree> <name> [slot]`: one full gate. Exit 0 pass, 1 fail, 3 infra down, 4 conflict with main.
- `gaterun.sh <repo-root>`: queue runner; pops `gateq.txt` lines `<name> <worktree-dir>`, honours `MAX_PARALLEL`.
- `monitor.sh [repo-name...]`: exits on the first PASS / FAIL / STALL (all repos when none given).
  Env: `STALL_SECS` (1800), `POLL` (60). A finished gate fires once.
- `testcap.sh <outfile> -- <cmd>`: caps scoped test runs at TESTCAP_MAX (2) per worktree+branch, full output to <outfile>, exit 3 when capped; `--reset` (orchestrator, per fix round), `--status`.
- `failsum.sh <lines-file>`: 3-line cheap-model diagnosis; "HARD" (>5 lines, timeouts, compile errors, conflicts) skips it.
- `overlap.sh <repo-root> <branches...>`: files two or more branches both change.
- `brief-template.md`: worker brief.

## .gate.conf reference
- `MAIN` (main), `MAX_PARALLEL` (1), `PARTS="a b"`.
- `ENV`: space-separated `K=V` exported for every step; `{DB}` (per-run db name) and `{N}` (slot) are replaced.
- `GUARDS`: lines `name|command`, always run in the worktree root.
- Per part `P` (variables are `P_X`): `PATHS` (regex; part runs only if changed vs main), `DIR` (cwd under worktree),
  `PRE` (infra precheck; fail = exit 3, part skipped), `SETUP` (lines `name|cmd`, before test), `TEST` (output saved in full),
  `PASS` (regex the test output tail must match), `CHECKS` (lines `name|cmd`, after test),
  `RETRY_IF` (regex in a failing step's output) + `RETRY_CLEAN` (command), then that step reruns once.
- Commands run in `bash` with `GATE_WT GATE_NAME GATE_DB GATE_N GATE_ROOT` set. `PRE` may be a function defined in the conf.
- Output: one `STEP <part>:<step> PASS|FAIL <tail>` line per step; skipped parts print `STEP <part>:skipped PASS`.

## Flow
```
echo "my-branch my-branch" >> ~/.cache/gate/<repo>/gateq.txt     # queue
nohup bash ~/code/dev-stack/scripts/gate/gaterun.sh <repo-root> >/dev/null 2>&1 &   # once
bash ~/code/dev-stack/scripts/gate/monitor.sh <repo>              # blocks; prints the verdict
```
Act: PASS = merge or continue; FAIL = read the printed step lines and names, fix, requeue; STALL = inspect the log.

## Token rules
- Never poll in the AI session; run `monitor.sh` once (background) and wake only on its output.
- Do not paste full logs; `full-<n>.txt` is read only for names the monitor did not give.
- Run `overlap.sh` before dispatching parallel workers; give each worker the brief template and a scoped test run only.
- The full gate runs from the queue, not from workers.
