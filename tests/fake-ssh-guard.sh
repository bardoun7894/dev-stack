#!/bin/sh
# Test guard: first `ssh` on PATH for every jdelegate test. Records "<host> <cmd...>" in $SSH_GUARD_LOG and fails for any
# host except the fake one, so a test can never reach a real machine (spec 002 D2).
while [ "$1" = -o ]; do shift 2; done
host=$1; shift
printf '%s\n' "$host $*" >> "${SSH_GUARD_LOG:-/dev/null}"
if [ "$host" = fake-host ]; then
  case "$*" in
    *"factory submit"*) cat >/dev/null; echo "proj:owner:g1:1";;
    *"frun start"*) echo "jdelegate:guard:1:1";;
  esac
  exit 0
fi
echo "ssh-guard: blocked ssh to $host" >&2
exit 1
