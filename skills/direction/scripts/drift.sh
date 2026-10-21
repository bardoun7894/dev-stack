#!/bin/bash
# drift.sh <repo> [--since <git-ref>]: zero-AI drift report (markdown on stdout). Read-only.
# Maps commits to specs/*/ and checks that each non-negotiable rule has an enforcing check.
set -u
repo="" since=""
while [ $# -gt 0 ]; do
  case "$1" in
    --since) since="${2:-}"; shift 2 ;;
    -h|--help) echo "usage: drift.sh <repo> [--since <git-ref>]"; exit 0 ;;
    *) repo="$1"; shift ;;
  esac
done
[ -n "$repo" ] && [ -d "$repo" ] || { echo "usage: drift.sh <repo> [--since <git-ref>]" >&2; exit 2; }
cd "$repo" || exit 2
git rev-parse --git-dir >/dev/null 2>&1 || { echo "not a git repo: $repo" >&2; exit 2; }
root=$(git rev-parse --show-toplevel); cd "$root" || exit 2
branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null)
head=$(git rev-parse HEAD 2>/dev/null) || { echo "no commits in $repo" >&2; exit 2; }

# ---- range ----
range_note=""
if [ -z "$since" ]; then
  for b in origin/main main origin/master master; do
    if git rev-parse --verify -q "$b" >/dev/null; then
      mb=$(git merge-base HEAD "$b" 2>/dev/null)
      if [ -n "$mb" ] && [ "$mb" != "$head" ]; then since="$mb"; range_note="merge-base with $b"; break; fi
    fi
  done
fi
if [ -z "$since" ]; then
  logargs="-30"; range_note="last 30 commits"
else
  git rev-parse --verify -q "$since^{commit}" >/dev/null || { echo "bad ref: $since" >&2; exit 2; }
  [ -n "$range_note" ] || range_note="--since $since"
  logargs="$since..HEAD"
fi

# ---- specs ----
specs=""   # lines: dir<TAB>title<TAB>open<TAB>done
if [ -d specs ]; then
  for d in specs/*/; do
    n=$(basename "$d"); case "$n" in _*) continue ;; esac
    title=$(awk '/^# /{sub(/^# +/,""); print; exit}' "$d/spec.md" 2>/dev/null)
    open=0; done_=0
    if [ -f "$d/tasks.md" ]; then
      open=$(grep -c '^[[:space:]]*[-*] \[ \]' "$d/tasks.md")
      done_=$(grep -c '^[[:space:]]*[-*] \[[xX]\]' "$d/tasks.md")
    fi
    specs="$specs$n	${title:-"(no spec.md title)"}	$open	$done_
"
  done
fi

echo "# Direction drift report"
echo
echo "- repo: $root"
echo "- branch: $branch"
echo "- range: $range_note"
echo "- generated: $(date +%Y-%m-%d)"
echo
echo "## Specs"
echo
if [ -z "$specs" ]; then echo "No specs/*/ directories found. Every commit will be UNMAPPED."; else
  echo "| spec | title | tasks open | tasks done |"
  echo "|---|---|---|---|"
  printf '%s' "$specs" | while IFS='	' read -r n t o dn; do echo "| $n | $t | $o | $dn |"; done
fi
echo

# ---- commits ----
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
git log --no-merges --name-only --format='@@%h%x09%s' $logargs 2>/dev/null > "$tmp/log"
total=0; mapped=0; housekeeping=0
: > "$tmp/rows"; : > "$tmp/unmapped"; : > "$tmp/hkrows"
# current branch equals a spec dir => branch mapping
branch_spec=""
printf '%s' "$specs" | cut -f1 > "$tmp/specnames"
while IFS= read -r n; do [ "$n" = "$branch" ] && branch_spec="$n"; done < "$tmp/specnames"
# task-path: exact file paths in backticks in specs/<n>/tasks.md (>=2 segments, has an extension)
: > "$tmp/taskpaths"
while IFS= read -r n; do
  [ -n "$n" ] && [ -f "specs/$n/tasks.md" ] || continue
  awk '{ k=split($0,a,"`"); for(i=2;i<=k;i+=2) if (a[i] ~ /^[A-Za-z0-9._-]+(\/[A-Za-z0-9._-]+)+\.[A-Za-z0-9]+$/) print a[i] }' "specs/$n/tasks.md" | sort -u | awk -v s="$n" '{print s "\t" $0}' >> "$tmp/taskpaths"
done < "$tmp/specnames"

flush() {
  [ -n "${sha:-}" ] || return 0
  total=$((total+1))
  lsub=$(printf '%s' "$subj" | tr '[:upper:]' '[:lower:]')
  nf=$(printf '%s' "$files" | grep -c .)
  fl=$(printf '%s' "$files" | grep . | head -4 | tr '\n' ' ')
  [ "$nf" -gt 4 ] && fl="$fl(+$((nf-4)) more)"
  printf '%s' "$files" > "$tmp/cfiles"
  # housekeeping first: not drift, own bucket, never sent to the judge
  hk=0
  case "$lsub" in docs\(kb\)*|docs\(specs\)*|chore\(kb\)*) hk=1 ;; esac
  if [ "$hk" = 0 ] && [ "$nf" -gt 0 ]; then
    hk=1
    while IFS= read -r f; do
      [ -n "$f" ] || continue
      case "$f" in ai-knowledge-base/*|specs/_session/*|specs/_direction/*|okf/*|docs/*.md) ;; *) hk=0; break ;; esac
    done < "$tmp/cfiles"
  fi
  if [ "$hk" = 1 ]; then
    housekeeping=$((housekeeping+1)); echo "| $sha | $subj | HOUSEKEEPING | $fl |" >> "$tmp/hkrows"
    return 0
  fi
  hit="" how=""
  while IFS= read -r n; do
    [ -n "$n" ] || continue
    ln=$(printf '%s' "$n" | tr '[:upper:]' '[:lower:]')
    num=$(printf '%s' "$n" | sed -n 's/^\([0-9][0-9]*\)-.*/\1/p')
    case "$lsub" in *"$ln"*) hit="$n"; how="subject"; break ;; esac
    if [ -n "$num" ] && printf '%s' "$lsub" | grep -Eq "(^|[^0-9])(spec[ -]?)?0*$num([^0-9]|$)" && printf '%s' "$lsub" | grep -Eq "spec|$num-|$num:|\\[$num\\]"; then hit="$n"; how="spec-id"; break; fi
  done < "$tmp/specnames"
  # spec-files: the spec dir holding the most of this commit's files (ties: first by name)
  if [ -z "$hit" ]; then
    hit=$(awk -v names="$tmp/specnames" 'BEGIN{while((getline l < names)>0) ok[l]=1} /^specs\// {split($0,p,"/"); if (p[2] in ok) c[p[2]]++} END{for(s in c) print c[s], s}' "$tmp/cfiles" | sort -k1,1nr -k2,2 | head -1 | awk '{print $2}')
    [ -n "$hit" ] && how="spec-files"
  fi
  if [ -z "$hit" ]; then
    tid=$(printf '%s' "$subj" | grep -Eo '\bT[0-9]{2,4}\b' | head -1)
    if [ -n "$tid" ]; then
      cnt=0; cand=""
      while IFS= read -r n; do
        [ -n "$n" ] && [ -f "specs/$n/tasks.md" ] && grep -q "\\b$tid\\b" "specs/$n/tasks.md" && { cnt=$((cnt+1)); cand="$n"; }
      done < "$tmp/specnames"
      [ "$cnt" = 1 ] && { hit="$cand"; how="T-number $tid"; }
    fi
  fi
  # task-path: a commit file is an exact backticked path in one spec's tasks.md (most files wins)
  if [ -z "$hit" ]; then
    hit=$(awk -F'\t' 'FNR==NR {want[$0]=1; next} ($2 in want) && !seen[$1 SUBSEP $2]++ {c[$1]++} END{for(s in c) print c[s], s}' "$tmp/cfiles" "$tmp/taskpaths" | sort -k1,1nr -k2,2 | head -1 | awk '{print $2}')
    [ -n "$hit" ] && how="task-path"
  fi
  if [ -z "$hit" ] && [ -n "$branch_spec" ]; then hit="$branch_spec"; how="branch"; fi
  if [ -n "$hit" ]; then
    mapped=$((mapped+1)); echo "| $sha | $subj | $hit ($how) | $fl |" >> "$tmp/rows"
  else
    echo "| $sha | $subj | UNMAPPED | $fl |" >> "$tmp/rows"
    echo "- $sha $subj  [$fl]" >> "$tmp/unmapped"
  fi
}
sha="" subj="" files=""
while IFS= read -r line; do
  case "$line" in
    @@*) flush; rest=${line#@@}; sha=${rest%%	*}; subj=${rest#*	}; subj=$(printf '%s' "$subj" | tr '|' '/'); files="" ;;
    "") ;;
    *) files="$files$line
" ;;
  esac
done < "$tmp/log"
flush

echo "## Commits"
echo
if [ "$((total-housekeeping))" = 0 ]; then echo "No commits in range outside housekeeping."; else
  echo "| sha | subject | spec | files |"
  echo "|---|---|---|---|"
  cat "$tmp/rows"
fi
echo
echo "## Housekeeping (not drift, not sent to the judge)"
echo
if [ "$housekeeping" = 0 ]; then echo "none"; else
  echo "| sha | subject | bucket | files |"
  echo "|---|---|---|---|"
  cat "$tmp/hkrows"
fi
echo
echo "## UNMAPPED commits (for the judge pass)"
echo
if [ -s "$tmp/unmapped" ]; then cat "$tmp/unmapped"; else echo "none"; fi
echo

# ---- non-negotiables ----
: > "$tmp/rules"
extract_section() { # file: rules under headings mentioning non-negotiable
  awk '
    function lvl(s,  m){ m=s; sub(/[^#].*/,"",m); return length(m) }
    /^#+ / {
      if (insec && lvl($0) <= seclvl) insec=0
      if (tolower($0) ~ /non-negotiable/) { insec=1; seclvl=lvl($0); head=$0; sub(/^#+ +/,"",head); nb=0; heads[++nh]=head; next }
    }
    insec && /^[[:space:]]*([-*]|[0-9]+[.)]) +/ { l=$0; sub(/^[[:space:]]*([-*]|[0-9]+[.)]) +/,"",l); print l; nb++ ; next }
    END{}
  ' "$1"
}
for f in CLAUDE.md .claude/CLAUDE.md AGENTS.md; do
  [ -f "$f" ] || continue
  extract_section "$f" | while IFS= read -r r; do printf '%s\t%s\n' "$f" "$r"; done >> "$tmp/rules"
  # heading-only rules (heading says non-negotiable, no bullets): use the heading itself
  grep -i '^#.*non-negotiable' "$f" | sed 's/^#* *//' | while IFS= read -r h; do
    grep -qF -- "$h" "$tmp/rules" || printf '%s\t%s\n' "$f" "$h" >> "$tmp/rules.h"
  done
  grep -i '^[-*].*NON-NEGOTIABLE' "$f" | sed 's/^[-*] *//' | while IFS= read -r r; do printf '%s\t%s\n' "$f" "$r"; done >> "$tmp/rules"
done
if [ -f .specify/memory/constitution.md ]; then
  awk '/^###+ /{l=$0; sub(/^#+ +/,"",l); print ".specify/memory/constitution.md\t" l}' .specify/memory/constitution.md >> "$tmp/rules"
fi
# heading-only rules only when the section had no bullets
[ -s "$tmp/rules.h" ] && cat "$tmp/rules.h" >> "$tmp/rules"
awk '!seen[$0]++' "$tmp/rules" > "$tmp/rules.u"

# candidate enforcement files
git ls-files 2>/dev/null | grep -Ei '(^|/)(tests?|__tests__|e2e|spec)/|\.(test|spec)\.[a-z]+$|(^|/)test_[^/]*$|eslint|ruff|\.pre-commit-config|(^|/)\.husky/|(^|/)\.githooks/|(^|/)hooks/|\.github/workflows/|\.gitlab-ci|lint|semgrep|sonar' | head -400 > "$tmp/checks"

stop=" which their there these those would should could shall about after before every other never always must without within using where while when then than that this with from have been into only also each does done will your ours they them what"
echo "## Non-negotiables"
echo
if [ ! -s "$tmp/rules.u" ]; then echo "No non-negotiables list found (CLAUDE.md heading with \"Non-negotiable\", or .specify/memory/constitution.md)."; else
  echo "Check = heuristic: a test/lint/hook/CI file that mentions >=2 of the rule's keywords. Confirm by hand."
  echo
  echo "| rule | source | status | check |"
  echo "|---|---|---|---|"
  nohas=0
  while IFS='	' read -r src rule; do
    clean=$(printf '%s' "$rule" | sed 's/[`*_]//g; s/\[[^]]*\]([^)]*)//g' | tr '[:upper:]' '[:lower:]')
    kws=$(printf '%s' "$clean" | tr -c 'a-z0-9\n' ' ' | tr ' ' '\n' | awk -v stop="$stop" 'length($0)>=5 && index(stop," "$0" ")==0 && !s[$0]++ {print length($0), $0}' | sort -rn | head -4 | awk '{print $2}')
    nk=$(printf '%s' "$kws" | grep -c .)
    need=2; [ "$nk" -lt 2 ] && need=$nk
    found=""
    if [ "$nk" -gt 0 ]; then
      while IFS= read -r cf; do
        [ -f "$cf" ] || continue
        c=0
        for k in $kws; do grep -qiF -- "$k" "$cf" 2>/dev/null && c=$((c+1)); done
        if [ "$c" -ge "$need" ]; then found="$cf"; break; fi
      done < "$tmp/checks"
    fi
    short=$(printf '%s' "$rule" | cut -c1-90 | tr '|' '/')
    if [ -n "$found" ]; then echo "| $short | $src | HAS-CHECK | $found |"
    else echo "| $short | $src | NO-CHECK | - |"; nohas=$((nohas+1)); fi
  done < "$tmp/rules.u"
  echo
  echo "NO-CHECK count: $nohas"
fi
echo
echo "## Summary"
echo
if [ "$((total-housekeeping))" -gt 0 ]; then pct=$((mapped*100/(total-housekeeping))); else pct=100; fi
echo "- commits: $total, mapped to a spec: $mapped, housekeeping: $housekeeping, UNMAPPED: $((total-mapped-housekeeping))"
echo "- mechanical on-plan: $pct% (mapped / (commits - housekeeping))"
