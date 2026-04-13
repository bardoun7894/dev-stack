#!/usr/bin/env bash
# Global UserPromptSubmit hook.
# 1. Walk up from cwd to find the project root (first ancestor with .git or .claude,
#    but never cross $HOME — we must not bootstrap into $HOME itself).
# 2. If no marker is found but cwd is a user-project candidate (under $HOME,
#    not $HOME itself), auto-run `git init` at cwd so the folder becomes a
#    recognized project root for this and future sessions.
# 3. If the project is missing ai-knowledge-base or .specify, inject a hard
#    bootstrap instruction telling Claude to run /kb-setup and/or /kb-spec init
#    before doing anything else.
# 4. Always append the standing-rule reminder for /kb-query and /kb-spec.

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

root=$(find_project_root) || root=""

auto_init_notice=""
if [ -z "$root" ]; then
  case "$PWD" in
    "$HOME") ;;
    "$HOME"/*)
      if command -v git >/dev/null 2>&1; then
        git init -q "$PWD" >/dev/null 2>&1
        if [ -d "$PWD/.git" ]; then
          root="$PWD"
          auto_init_notice="AUTO-INITIALIZED an empty git repo at $PWD because no .git or .claude marker was present. Tell the user once that you ran \`git init\` here, then continue.\n\n"
        fi
      fi
      ;;
  esac
fi

if [ -n "$auto_init_notice" ]; then
  printf '%b' "$auto_init_notice"
fi

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

printf '%s\n' 'REMINDER (standing rule from ~/.claude/CLAUDE.md): Before answering any question about project history, prior decisions, architecture, past bugs, or existing features, silently run /kb-query first and ground the reply in the cited [[wikilinks]]. Before any /speckit.* phase, run the matching /kb-spec phase first (pre before specify, plan before plan, tasks before tasks, implement before implement). Run /kb-spec post after /speckit.tasks. These are standing bridges — do not wait for explicit invocation.'
