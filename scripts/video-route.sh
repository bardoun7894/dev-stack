#!/usr/bin/env bash
# video-route [--project DIR] "<brief>" -> prints remotion | hyperframes | ask-opus
set -u
DIR="$PWD"
if [ "${1:-}" = "--project" ]; then DIR="${2:-$PWD}"; shift 2; fi
BRIEF="${1:-}"

is_remotion() {
  local d root
  d="$(cd "$1" 2>/dev/null && pwd)" || return 1
  root="$(git -C "$d" rev-parse --show-toplevel 2>/dev/null || true)"
  while :; do
    [ -f "$d/remotion.config.ts" ] && return 0
    if [ -f "$d/package.json" ] && grep -Eq '"(remotion|@remotion/[^"]+)"[[:space:]]*:' "$d/package.json"; then return 0; fi
    { [ "$d" = "$root" ] || [ "$d" = "/" ] || [ -z "$root" ]; } && return 1
    d="$(dirname "$d")"
  done
}

if is_remotion "$DIR"; then echo remotion; exit 0; fi

out=$(jev choice "Which renderer builds this video" \
  hyperframes="one-off promo, launch, explainer, kinetic typography, GSAP motion, short social ad" \
  remotion="many variants from one template, data-driven, captions from transcript, charts or maps" \
  -s "$BRIEF" --min 0.75 -q 2>/dev/null)
rc=$?
case $rc in
  0) case "$out" in hyperframes|remotion) echo "$out"; exit 0;; esac; echo ask-opus; exit 3;;
  2) echo ask-opus; exit 2;;
  *) echo ask-opus; exit 3;;
esac
