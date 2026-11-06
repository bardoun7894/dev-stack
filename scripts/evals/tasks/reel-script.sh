#!/bin/bash
# Day 7 reel in Moroccan Darija: deterministic rule checks, then a Jev language check.
cd /tmp || exit 1
ans="$(perl -e 'alarm shift; exec @ARGV' 180 claude -p "اكتب سكريبت ريل لليوم 7 بالدارجة المغربية. القواعد: 2 إلى 3 جمل منطوقة فقط، آخر جملة هي بالضبط «غدا: النهار 8»، بلا دعوة للتحرك (CTA)، بلا DM، بلا ثمن. اعطيني النص فقط." </dev/null 2>&1)" || { echo "claude failed"; exit 1; }
printf '%s' "$ans" | grep -q "غدا: النهار 8" || { echo "missing closing line"; exit 1; }
printf '%s' "$ans" | grep -qiE 'DM|link in bio|درهم' && { echo "forbidden term present"; exit 1; }
p="$(printf '%s' "$ans" | jev noul "this text is Moroccan Darija" -q 2>&1)"; rc=$?
[ "$rc" = 0 ] || { echo "jev error rc=$rc"; exit 1; }
echo "rules ok, darija p=$p"
awk -v p="$p" 'BEGIN{exit !(p>=0.6)}'
