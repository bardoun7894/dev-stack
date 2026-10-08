#!/usr/bin/env bash
# Test for skills/market-swot/scripts/design-audit.sh
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
SCRIPT="$HERE/../../skills/market-swot/scripts/design-audit.sh"
fail=0
command -v jq >/dev/null || { echo "FAIL jq not installed"; exit 1; }
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
mkdir -p "$T/repo/src" "$T/bin"; cd "$T/repo" || exit 1
git init -q; git config user.email t@e.com; git config user.name T
echo '{"dependencies":{"tailwindcss":"^2.0.0","framer-motion":"^6.0.0","jquery":"^3.0.0","bootstrap":"^4.6.0","left-pad":"1.0.0"}}' > package.json
printf '.a{color:red !important}\n.b{margin:12px;padding:8px !important}\n' > src/app.css
printf '<div style="color:red">x</div>\n' > src/index.html
echo '# design' > DESIGN.md; echo '{}' > tokens.json
git add -A; git commit -q -m fx
cat > "$T/bin/npm" <<'E'
#!/usr/bin/env bash
[ "$1" = view ] && { echo "9.9.9"; exit 0; }
exit 1
E
chmod +x "$T/bin/npm"

bash "$SCRIPT" >/dev/null 2>&1; [ $? -eq 2 ] || { echo "FAIL no-arg exit want=2"; fail=1; }
out="$(PATH="$T/bin:$PATH" bash "$SCRIPT" "$T/repo")"; rc=$?
[ "$rc" -eq 0 ] || { echo "FAIL exit=$rc"; fail=1; }
echo "$out" | jq . >/dev/null 2>&1 || { echo "FAIL not JSON"; echo "$out"; exit 1; }
for k in deps lighthouse axe design_md tokens_file signals; do
  echo "$out" | jq -e "has(\"$k\")" >/dev/null || { echo "FAIL key $k"; fail=1; }
done
[ "$(echo "$out" | jq -r '.deps[] | select(.pkg=="tailwindcss") | .latest')" = "9.9.9" ] || { echo "FAIL tailwind latest"; fail=1; }
[ "$(echo "$out" | jq -r '.deps[] | select(.pkg=="tailwindcss") | .outdated')" = "true" ] || { echo "FAIL tailwind outdated"; fail=1; }
echo "$out" | jq -e '[.deps[].pkg] | index("left-pad") == null' >/dev/null || { echo "FAIL unrelated pkg listed"; fail=1; }
[ "$(echo "$out" | jq -r .lighthouse)" = "null" ] || { echo "FAIL lighthouse want null"; fail=1; }
[ "$(echo "$out" | jq -r .axe)" = "null" ] || { echo "FAIL axe want null"; fail=1; }
[ "$(echo "$out" | jq -r .design_md)" = "DESIGN.md" ] || { echo "FAIL design_md"; fail=1; }
[ "$(echo "$out" | jq -r .tokens_file)" = "tokens.json" ] || { echo "FAIL tokens_file"; fail=1; }
[ "$(echo "$out" | jq -r .signals.jquery)" = "true" ] || { echo "FAIL jquery"; fail=1; }
[ "$(echo "$out" | jq -r .signals.bootstrap)" = "true" ] || { echo "FAIL bootstrap"; fail=1; }
[ "$(echo "$out" | jq -r .signals.important_count)" = "2" ] || { echo "FAIL important want=2 got=$(echo "$out" | jq -r .signals.important_count)"; fail=1; }
[ "$(echo "$out" | jq -r .signals.inline_style_count)" = "1" ] || { echo "FAIL inline_style want=1"; fail=1; }
[ "$(echo "$out" | jq -r .signals.reduced_motion_missing)" = "true" ] || { echo "FAIL reduced_motion_missing"; fail=1; }
# offline: npm failing -> latest null, still valid
printf '#!/usr/bin/env bash\nexit 1\n' > "$T/bin/npm"
out3="$(PATH="$T/bin:$PATH" bash "$SCRIPT" "$T/repo")"
[ "$(echo "$out3" | jq -r '.deps[] | select(.pkg=="tailwindcss") | .latest')" = "null" ] || { echo "FAIL offline latest want null"; fail=1; }

[ "$fail" -eq 0 ] && echo "PASS all market-swot design_audit_test.sh assertions"
exit $fail
