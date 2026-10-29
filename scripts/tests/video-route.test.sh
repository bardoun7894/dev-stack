#!/usr/bin/env bash
# Tests for video-route.sh using a stub jev on PATH.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
SCRIPT="$HERE/../video-route.sh"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
mkdir -p "$T/bin" "$T/rem" "$T/plain"
echo '{"dependencies":{"@remotion/cli":"4.0.0"}}' > "$T/rem/package.json"
echo '{"name":"x"}' > "$T/plain/package.json"
(cd "$T/plain" && git init -q)
fail=0
mkstub() { # mode
  cat > "$T/bin/jev" <<S
#!/usr/bin/env bash
echo called >> "$T/calls"
case "$1" in
  ok) echo hyperframes; exit 0;;
  *) exit ${2:-0};;
esac
S
}
stub() { printf '#!/usr/bin/env bash\necho called >> "%s/calls"\n%s\n' "$T" "$1" > "$T/bin/jev"; chmod +x "$T/bin/jev"; rm -f "$T/calls"; }
check() { # name want_out want_rc got_out got_rc
  if [ "$2" = "$4" ] && [ "$3" = "$5" ]; then echo "PASS $1"; else echo "FAIL $1: want '$2'/$3 got '$4'/$5"; fail=1; fi
}
run() { out=$(PATH="$T/bin:$PATH" "$SCRIPT" "$@" 2>/dev/null); rc=$?; }

stub 'echo hyperframes'; run --project "$T/rem" "brief"
check remotion-project remotion 0 "$out" $rc
[ ! -e "$T/calls" ] && echo "PASS stub-not-called" || { echo "FAIL stub called"; fail=1; }

stub 'echo hyperframes'; run --project "$T/plain" "brief"
check stub-hyperframes hyperframes 0 "$out" $rc
stub 'echo remotion'; run --project "$T/plain" "brief"
check stub-remotion remotion 0 "$out" $rc
stub 'exit 2'; run --project "$T/plain" "brief"
check low-confidence ask-opus 2 "$out" $rc
stub 'exit 3'; run --project "$T/plain" "brief"
check jev-error ask-opus 3 "$out" $rc
stub 'echo garbage; exit 0'; run --project "$T/plain" "brief"
check unparseable ask-opus 3 "$out" $rc

echo "--- real jev"
out=$("$SCRIPT" --project "$T/plain" "30-second launch teaser for a perfume brand with animated text"); echo "real: $out (rc=$?)"
exit $fail
