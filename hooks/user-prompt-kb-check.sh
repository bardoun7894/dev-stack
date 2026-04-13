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
    if [ -d "$dir/.git" ] || [ -d "$dir/.claude" ]; then
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

# --- Bootstrap alert (always fires when toolchains missing) ---
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
