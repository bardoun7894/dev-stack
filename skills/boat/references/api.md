# boat.dev API contract (verified 2026-11-03 against docs.boat.dev/llms-full.txt)

Base `https://boat.dev/api/v1`. Header `Authorization: Bearer <key>`. Responses carry `ok` and `type`;
errors are `{ok:false,type:"sandbox.error",error:{...}}` with the HTTP status as primary signal.
The per-endpoint reference pages in llms-full.txt are stubs (no schemas); fields below come from the guide pages.

## Sandboxes
- `POST /sandboxes` body `{ttlSeconds, type, from, env, environment}`; `Idempotency-Key` header makes retries safe. Returns `{sandbox:{id:"bx_..."}}`. Size field is `type`.
- `GET /sandboxes` -> `{sandboxes:[...]}`. `GET /sandboxes/{id}` -> `sandbox.state`; poll until `ready|idle|running`.
- `POST /sandboxes/{id}/stop` (disk snapshot kept, 14+ days; stop ends at `stopped`/`archived`), `/resume` (`type`, `ttlSeconds`), `/fork`.
- `DELETE /sandboxes/{id}` requires header `X-Ascii-Confirm-Delete: <id>`; returns 202 `{operation:{id:"bdop_...",status}}`. Poll `GET /deletion-operations/{opId}` until `operation.status == completed` (pending|processing|blocked|completed).
- Sizes: `small` (2 vCPU/4 GB, $0.018/h), `default` (4/8, $0.036/h), `large` (8/16), `xlarge` (16/32, needs $100 plan). ttl max 30 days; `ttlSeconds` is not an idle timeout. Region: EU only, not selectable.

## Commands
- `POST /sandboxes/{id}/commands` `{command, cwd, timeoutSeconds (default 30, max 600), stream, detached}`. Sync reply: `{exitCode, stdout, stderr, timedOut, oomKilled}`.
- `detached:true` -> `{type:"command.started", processId}`. `GET .../commands/{processId}?stdoutOffset=&stderrOffset=` -> `{running, exitCode, stdout, stderr, stdoutNextOffset, stderrNextOffset, more}`. `DELETE` kills it. `GET .../commands/{pid}/stream` attaches (NDJSON).

## Files
- Paths relative to `/home/user`; absolute only under `/home/user` or `/tmp` (else 400 `invalid_path`).
- `GET|PUT /files` JSON calls up to 5 MiB. `POST /files/upload-url` / `download-url` body `{path, ttlSeconds?}` -> `{url, method}`; PUT raw bytes to the URL with no Authorization header. 15 min default, max 3600. URLs are secrets.

## CI
- `POST /ci/connect` links GitHub; `GET /ci`, `/ci/jobs/{id}`, `/ci/jobs/{id}/logs`, `POST /ci/public`.
- Workflow label: `runs-on: boat` (default size), `boat-small|boat-large|boat-xlarge`; options after `/` e.g. `boat-large/from=ci-base/debug`. Max 6 h per job. Public repos are off by default. Jobs get no boat env or secrets; use GitHub Actions secrets.

## Differences from the brief
- Work dir is `/home/user`, `/workspace` is not writable by the API rules: push extracts to `~/workspace/<dirname>`.
- Delete needs the confirm header. Size field is `type`. Detached poll uses byte offsets.
