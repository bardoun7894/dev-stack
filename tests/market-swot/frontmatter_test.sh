#!/usr/bin/env bash
# SKILL.md frontmatter must be valid YAML with name == market-swot
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
F="$HERE/../../skills/market-swot/SKILL.md"
fm="$(awk 'NR==1&&/^---$/{f=1;next} f&&/^---$/{exit} f' "$F")"
name=""
if python3 -c 'import yaml' 2>/dev/null; then
  name="$(printf '%s\n' "$fm" | python3 -c 'import yaml,sys; print(yaml.safe_load(sys.stdin)["name"])' 2>&1)"
elif command -v ruby >/dev/null; then
  name="$(printf '%s\n' "$fm" | ruby -ryaml -e 'puts YAML.safe_load(STDIN.read)["name"]' 2>&1)"
else echo "FAIL no yaml parser"; exit 1; fi
[ "$name" = "market-swot" ] || { echo "FAIL frontmatter name want=market-swot got=$name"; exit 1; }
echo "PASS frontmatter_test.sh name=market-swot"
