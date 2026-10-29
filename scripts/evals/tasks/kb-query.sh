#!/bin/bash
# Known answer in the KB (qa/tokyo-server-free-models...): Tokyo's Claude Code runs on Kimi.
cd "$HOME/projects/ai-knowledge-base" || { echo "kb dir missing"; exit 2; }
ans="$(perl -e 'alarm shift; exec @ARGV' 240 uv run python scripts/query.py "Which model does the Tokyo server's Claude Code run on?" 2>&1 </dev/null)" || { echo "query failed: $(printf '%s' "$ans" | tail -1 | cut -c1-120)"; exit 1; }
if printf '%s' "$ans" | grep -qi kimi; then echo "answer mentions Kimi"; else echo "no 'kimi' in answer"; exit 1; fi
