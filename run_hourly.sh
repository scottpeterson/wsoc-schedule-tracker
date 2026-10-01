#!/bin/bash
# Hourly entry point for launchd on the Mac: sync with the repo, check schedules,
# rebuild docs/, notify about any new change events, publish.
set -u
cd "$(dirname "$0")" || exit 1
PY=/opt/homebrew/bin/python3
HAS_REMOTE=0
if git rev-parse --is-inside-work-tree >/dev/null 2>&1 && git remote get-url origin >/dev/null 2>&1; then
  HAS_REMOTE=1
  git pull -q --rebase --autostash origin main || echo "[$(date '+%F %T')] pull failed, continuing with local state"
fi
$PY check_schedules.py
$PY build_site.py
$PY notify_new_events.py
if [ "$HAS_REMOTE" = 1 ] && [ -n "$(git status --porcelain)" ]; then
  git add -A
  git commit -q -m "Hourly check $(date '+%Y-%m-%d %H:%M')"
  git push -q origin HEAD && echo "[$(date '+%F %T')] pushed"
fi
