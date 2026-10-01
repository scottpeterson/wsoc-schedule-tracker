#!/bin/bash
# Hourly entry point for launchd on the Mac.
# With a remote: the GitHub Actions workflow does the checking and committing, so this
# job only pulls the latest state and raises a macOS notification for new change events.
# Without a remote (local-only use): check, build, notify here.
set -u
cd "$(dirname "$0")" || exit 1
PY=/opt/homebrew/bin/python3
if git rev-parse --is-inside-work-tree >/dev/null 2>&1 && git remote get-url origin >/dev/null 2>&1; then
  git fetch -q origin main && git reset -q --hard origin/main || echo "[$(date '+%F %T')] fetch failed, notifying from local state"
else
  $PY check_schedules.py
  $PY build_site.py
fi
$PY notify_new_events.py
