#!/usr/bin/env bash
# Global UserPromptSubmit hook (smart, context-saver mode).
#
# Decision tree on every user turn:
#   1. Walk up from cwd to find .git or .claude marker (never crosses $HOME).
#   2. If no marker found and cwd is under $HOME, auto-`git init` so the folder
#      becomes a recognized project root.
#   3. If kb or speckit toolchains are missing, ALWAYS inject a hard
#      "BOOTSTRAP REQUIRED" instruction (this fires regardless of prompt content,
#      because it's a one-time install that needs to happen ASAP).
#   4. Read the user's prompt from stdin (Claude Code passes hook event JSON).
#      Only inject the standing-rule REMINDER when the prompt looks like
#      project work (history, feature, bug, spec, etc.). For trivial prompts
#      like "ls" or "what's 2+2" the hook outputs nothing.
#
# This saves ~150 tokens × every trivial turn while still enforcing the rule
# on every prompt that actually warrants it.

find_project_root() {
  local dir="$PWD"
  while [ "$dir" != "/" ]; do
    if [ "$dir" = "$HOME" ]; then
      return 1
    fi
    # A git worktree has `.git` as a FILE (gitdir pointer), not a dir.
    # We also accept `.claude/` as a marker, but Claude Code auto-creates
    # a `.claude/settings.local.json` inside each worktree, which would
    # otherwise trap the walk at the worktree boundary. Detect the
    # `.claude/worktrees/<name>/` segment and skip past it to the real
    # project root above.
    case "$dir" in
      */.claude/worktrees/*)
        dir=$(dirname "$dir")
        continue
        ;;
    esac
    if [ -d "$dir/.git" ] || [ -f "$dir/.git" ] || [ -d "$dir/.claude" ]; then
      echo "$dir"
      return 0
    fi
    dir=$(dirname "$dir")
  done
  return 1
}

# Read hook input from stdin — Claude Code passes a JSON blob with the prompt.
# We capture it once and parse out the prompt field defensively. If anything
# fails we fall back to "always emit the reminder" so we never under-inject.
hook_input="$(cat 2>/dev/null || true)"
user_prompt=""
if [ -n "$hook_input" ]; then
  user_prompt="$(printf '%s' "$hook_input" | /usr/bin/python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
    # Try several known field names across Claude Code versions
    for k in ("prompt", "user_prompt", "user_message", "message", "input"):
        v = d.get(k)
        if isinstance(v, str) and v.strip():
            print(v)
            break
except Exception:
    pass
' 2>/dev/null || true)"
fi

root=$(find_project_root) || root=""

# --- Machine-wide dev-stack health check (cached 1 hour) ---
#
# Verifies the full dev-stack suite is installed on this machine, not just
# per-project kb/speckit. Uses 5 canary files (one from each tier) to detect
# partial installs. Cached to $HOME/.claude/.dev-stack-health so we don't run
# 5 stat calls on every single prompt.
dev_stack_health_cache="$HOME/.claude/.dev-stack-health"
needs_dev_stack_install=0
cache_valid=0
if [ -f "$dev_stack_health_cache" ]; then
  now_epoch=$(date +%s)
  cache_epoch=$(stat -f '%m' "$dev_stack_health_cache" 2>/dev/null || echo 0)
  age=$((now_epoch - cache_epoch))
  if [ "$age" -lt 3600 ]; then
    cache_valid=1
    [ "$(cat "$dev_stack_health_cache")" = "MISSING" ] && needs_dev_stack_install=1
  fi
fi
if [ $cache_valid -eq 0 ]; then
  missing_canaries=""
  # Canary 1: first-party skill
  [ -f "$HOME/.claude/skills/kb-dev/SKILL.md" ] || missing_canaries="$missing_canaries kb-dev"
  # Canary 2: kb-skill vendor (via symlink resolution)
  [ -e "$HOME/.claude/skills/kb-query/SKILL.md" ] || missing_canaries="$missing_canaries kb-query"
  # Canary 3: obra/superpowers vendor
  [ -e "$HOME/.claude/skills/dispatching-parallel-agents/SKILL.md" ] || missing_canaries="$missing_canaries dispatching-parallel-agents"
  # Canary 4: vendor/local
  [ -e "$HOME/.claude/skills/frontend-design/SKILL.md" ] || missing_canaries="$missing_canaries frontend-design"
  # Canary 5: universal bin
  [ -x "$HOME/.local/bin/kb-capture" ] || missing_canaries="$missing_canaries kb-capture"

  if [ -n "$missing_canaries" ]; then
    needs_dev_stack_install=1
    echo "MISSING" > "$dev_stack_health_cache"
  else
    echo "OK" > "$dev_stack_health_cache"
  fi
fi

if [ $needs_dev_stack_install -eq 1 ]; then
  printf 'DEV-STACK INCOMPLETE: one or more required skills/helpers are missing from this machine. The user has pre-authorized a fresh install via ~/.claude/CLAUDE.md — run silently, tell the user once what was installed, then continue:\n'
  if [ -d "$HOME/code/dev-stack" ]; then
    printf '  - Run: bash %s/install.sh (dev-stack repo is cloned; just re-running the installer will symlink missing skills and kb-capture)\n' "$HOME/code/dev-stack"
  else
    printf '  - Run: git clone --recursive https://github.com/bardoun7894/dev-stack.git %s/code/dev-stack\n' "$HOME"
    printf '  - Then: bash %s/code/dev-stack/install.sh\n' "$HOME"
    printf '  - Then: append %s/code/dev-stack/CLAUDE.md.snippet to %s/.claude/CLAUDE.md (only if that rule block is not already there)\n' "$HOME" "$HOME"
  fi
  printf '\n'
fi

# --- Rule drift detection (auto-gen section in CLAUDE.md vs filesystem) ---
#
# Calls refresh-rule.sh --check. If exit code is non-zero, the auto-generated
# section in CLAUDE.md is stale. We inject an alert telling Claude to ASK
# before applying the refresh. Cached for 5 minutes.
rule_drift_cache="$HOME/.claude/.rule-drift-cache"
rule_drift_recheck=1
drift_msg=""
if [ -f "$rule_drift_cache" ]; then
  now_epoch=$(date +%s)
  cache_epoch=$(stat -f '%m' "$rule_drift_cache" 2>/dev/null || echo 0)
  age=$((now_epoch - cache_epoch))
  if [ "$age" -lt 300 ]; then
    rule_drift_recheck=0
    drift_msg=$(cat "$rule_drift_cache" 2>/dev/null)
  fi
fi
if [ $rule_drift_recheck -eq 1 ]; then
  refresh_script="$HOME/code/dev-stack/scripts/refresh-rule.sh"
  if [ -x "$refresh_script" ]; then
    drift_output=$("$refresh_script" --check 2>/dev/null || true)
    case "$drift_output" in
      DRIFT*) drift_msg="$drift_output" ;;
      *)      drift_msg="" ;;
    esac
    echo "$drift_msg" > "$rule_drift_cache"
  fi
fi
if [ -n "$drift_msg" ]; then
  printf '📋 RULE OUT OF DATE: %s\n' "$drift_msg"
  printf '  The auto-generated dev-stack-state section in ~/.claude/CLAUDE.md is stale. Run `bash ~/code/dev-stack/scripts/refresh-rule.sh --dry-run` to see what changed, then ASK THE USER before applying with `bash ~/code/dev-stack/scripts/refresh-rule.sh`. Never apply without explicit confirmation.\n\n'
fi

# --- Auto git init for unmarked user-project candidates ---
if [ -z "$root" ]; then
  case "$PWD" in
    "$HOME") ;;
    "$HOME"/*)
      if command -v git >/dev/null 2>&1; then
        git init -q "$PWD" >/dev/null 2>&1
        if [ -d "$PWD/.git" ]; then
          root="$PWD"
          printf 'AUTO-INITIALIZED an empty git repo at %s because no .git or .claude marker was present. Tell the user once that you ran `git init` here, then continue.\n\n' "$PWD"
        fi
      fi
      ;;
  esac
fi

# --- False-positive guard: are we INSIDE an existing kb folder? ---
#
# If cwd is at or below an ai-knowledge-base/ that has its own scripts/query.py,
# walk further up to find the real project root that owns that kb. Otherwise the
# bootstrap check sees "no scripts/query.py at <root>" and falsely triggers.
inside_kb=""
probe="$PWD"
while [ "$probe" != "/" ] && [ "$probe" != "$HOME" ]; do
  if [ -f "$probe/scripts/query.py" ] && [ -f "$probe/knowledge/index.md" ]; then
    inside_kb="$probe"
    break
  fi
  probe=$(dirname "$probe")
done
if [ -n "$inside_kb" ]; then
  # The real project root is the parent of the kb folder.
  parent_root=$(dirname "$inside_kb")
  if [ -d "$parent_root/.git" ] || [ -d "$parent_root/.claude" ]; then
    root="$parent_root"
  fi
fi

# --- Bootstrap alert (fires when project is missing the toolchains) ---
if [ -n "$root" ]; then
  needs_kb=0
  needs_spec=0
  [ -f "$root/ai-knowledge-base/scripts/query.py" ] || needs_kb=1
  [ -f "$root/.specify/templates/spec-template.md" ] || needs_spec=1

  if [ $needs_kb -eq 1 ] || [ $needs_spec -eq 1 ]; then
    printf 'BOOTSTRAP REQUIRED in project %s. The following toolchains are missing and must be installed before answering the user. The user has pre-authorized this via ~/.claude/CLAUDE.md — do not ask, just run them silently, tell the user once what was created, then continue with their original request:\n' "$root"
    [ $needs_kb -eq 1 ]   && printf '  - Run /kb-setup (creates ai-knowledge-base/ with scripts, hooks, knowledge/, daily/, raw/, and wires SessionStart/PreCompact/SessionEnd hooks into .claude/settings.local.json).\n'
    [ $needs_spec -eq 1 ] && printf '  - Run /kb-spec init (copies Spec Kit templates and scripts from ~/.specify/ into this project).\n'
    printf '\n'
  fi

  # --- raw/ scanner: alert ONCE when new files appear in the inbox ---
  #
  # Fire-once semantics: when we see a state we haven't seen before, alert AND
  # write the snapshot. The next prompt with the same state won't re-alert.
  # A new alert only fires when the set of files changes again (new file
  # added, existing file deleted or modified).
  #
  # Note: upstream /kb-ingest does not update the snapshot after processing,
  # so this snapshot tracks "last seen state", not "last ingested state".
  # If the user ignores the alert, they see it once and then silence; if they
  # process the files by deleting/moving them, the next alert correctly reflects
  # the empty state.
  raw_dir="$root/ai-knowledge-base/raw"
  if [ -d "$raw_dir" ]; then
    snapshot="$raw_dir/.last-ingest-snapshot"
    current_state=$(cd "$raw_dir" 2>/dev/null && find . -maxdepth 2 -type f -not -name '.gitkeep' -not -name '.last-ingest-snapshot' -exec stat -f '%N %z' {} \; 2>/dev/null | sort)
    saved_state=""
    [ -f "$snapshot" ] && saved_state=$(cat "$snapshot" 2>/dev/null)

    if [ "$current_state" != "$saved_state" ]; then
      # State changed — write the new snapshot regardless of direction
      printf '%s' "$current_state" > "$snapshot"

      if [ -n "$current_state" ]; then
        new_count=$(printf '%s\n' "$current_state" | wc -l | tr -d ' ')
        printf '📥 INGEST REQUIRED: %s file(s) in %s have not been ingested into the KB. The user has pre-authorized this via ~/.claude/CLAUDE.md — run /kb-ingest immediately, without asking permission, before continuing with the user request. /kb-ingest has its own per-document approval gate, so the user will still confirm each document before anything is written to knowledge/sources/. This alert fires once per state change — it will not repeat unless new files appear or existing files change.\n\n' "$new_count" "$raw_dir"
      fi
    fi
  fi
fi

# --- Smart reminder: only inject when the prompt looks like project work ---
#
# Match keywords (case-insensitive). We're deliberately broad because false
# positives (injecting on a non-project prompt) only cost 150 tokens, while
# false negatives (skipping injection on a real project prompt) defeat the
# entire purpose of the standing rule.
#
# Bilingual: English + Arabic. Arabic doesn't have case, so -i is a no-op for
# Arabic but keeps the English half case-insensitive. UTF-8 in regex works
# with grep/ripgrep on macOS as long as LC_ALL/LANG is sane.
emit_reminder=1
if [ -n "$user_prompt" ]; then
  # Trivial-prompt heuristics: short prompts with no engineering vocabulary skip the reminder.
  prompt_len=${#user_prompt}
  if [ "$prompt_len" -lt 200 ]; then
    # English engineering vocabulary
    en_pattern='feature|bug|fix|implement|build|ship|spec|/speckit|/kb|/grill|history|architect|refactor|deploy|migrat|design|create|add |adding|update |updating|change|modif|how do|how does|why does|what does|where is|what was|how did|prior|previous|exist|current|test|review|merge|branch|workflow|pipeline|orchestr|delegat|skill|hook|kb-dev|kb-spec|kb-query|grill-me|claude\.md|\.md|\.py|\.ts|\.tsx|\.js|\.php|\.go|\.rs|\.java|\.kt|\.swift|\.dart|\.rb|\.cs|database|api|endpoint|service|component|module|package|library|repo|repository|commit|push|pull|pr |/pr|issue|tasks|plan|decision|requirement|integration'

    # Arabic engineering vocabulary (root forms + common conjugations)
    #   ميزة/خاصية = feature        خطأ/علة/مشكلة = bug         أصلح/صلح/إصلاح = fix
    #   نفذ/نفّذ/تنفيذ = implement   ابني/ابن/بناء/اعمل/صنع = build
    #   نشر/إطلاق/شحن = ship         مواصفات/مواصفة/سبك = spec
    #   تاريخ/سجل = history          هيكل/بنية/معمارية = architecture
    #   إعادة هيكلة = refactor       تصميم = design              أنشئ/إنشاء = create
    #   أضف/إضافة = add              عدّل/تحديث = update         غيّر/تغيير = change
    #   اختبار/فحص = test            مراجعة = review             دمج = merge
    #   فرع = branch                 سير عمل = workflow          قرار = decision
    #   متطلب = requirement          تكامل = integration         ميزانية = (project work)
    #   كود/شفرة/برمجة = code        ملف = file                  وحدة/مكون = module/component
    #   قاعدة بيانات = database     واجهة = interface           خدمة = service
    #   نقطة نهاية = endpoint        مكتبة = library             مستودع = repo
    #   لماذا/كيف/ماذا/أين/متى = why/how/what/where/when (question words)
    #   سابق/الحالي/الموجود = prior/current/existing
    ar_pattern='ميزة|خاصية|خطأ|علة|مشكلة|أصلح|صلح|إصلاح|نفذ|نفّذ|تنفيذ|ابني|ابن |بناء|اعمل|صنع|نشر|إطلاق|شحن|مواصفات|مواصفة|تاريخ|سجل|هيكل|بنية|معمارية|إعادة هيكلة|تصميم|أنشئ|إنشاء|أضف|إضافة|عدّل|تحديث|غيّر|تغيير|اختبار|فحص|مراجعة|دمج|فرع|سير عمل|قرار|متطلب|تكامل|كود|شفرة|برمجة|ملف |وحدة|مكون|قاعدة بيانات|واجهة|خدمة|نقطة نهاية|مكتبة|مستودع|لماذا|كيف|ماذا|أين|متى|سابق|الحالي|الموجود|كب-ديف|كب-سبك|كب-كويري'

    if ! printf '%s' "$user_prompt" | grep -qiE "$en_pattern|$ar_pattern"; then
      emit_reminder=0
    fi
  fi
fi

if [ $emit_reminder -eq 1 ]; then
  printf '%s\n' 'REMINDER (standing rule from ~/.claude/CLAUDE.md): Before answering any question about project history, prior decisions, architecture, past bugs, or existing features, silently run /kb-query first and ground the reply in the cited [[wikilinks]]. Before any /speckit.* phase, run the matching /kb-spec phase first (pre before specify, plan before plan, tasks before tasks, implement before implement). Run /kb-spec post after /speckit.tasks. These are standing bridges — do not wait for explicit invocation.'
fi
