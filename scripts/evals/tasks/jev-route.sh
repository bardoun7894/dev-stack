#!/bin/bash
# Routing follows the tier definitions in bin/jev: classification -> T0, any coding -> T3.
route() { jev route "$1" 2>&1 | jq -r .choice 2>/dev/null; }
a="$(route "label this email as spam or not spam")"
b="$(route "rename a variable in one file")"
echo "classify=$a code=$b"
[ "$a" = T0 ] && [ "$b" = T3 ]
