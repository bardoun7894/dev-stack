# Brief: market research worker (one pass)

Role: researcher. Read-only. One pass, no retries, no sub-agents.
Inputs: `<INVENTORY_JSON_PATH>`, candidates `<NAMES+URLS>`, subject `<SUBJECT>`, output dir `<OUT_DIR>`.
Task: for each candidate, fill the competitor-matrix columns (see skills/market-swot/references/competitor-matrix.md)
from fetched pages only. Cite every URL. Mark unknown fields "unknown", never guess.
Write ONLY: `<OUT_DIR>/competitors.json` and `<OUT_DIR>/matrix.md`. Do not touch repo, specs, or other files.
Do not: log in, scrape at volume, copy assets.
Acceptance: competitors.json is valid JSON (jq .), every non-unknown field has a source URL.
Report: <=150 words: files written, candidates covered, gaps.
