#!/bin/bash
# check-hook.sh: run the 15 hook cases and print PASS 15/15 or each mismatch. Zero AI.
bash "$(dirname "$0")/hooktest.sh" | awk '{split($1,a,"="); want=($0 ~ /expect 2/)?2:0; n++; if (a[2]!=want) {bad++; print "MISMATCH " $0}} END{print (bad? "FAIL " bad "/" n : "PASS " n "/" n)}'
