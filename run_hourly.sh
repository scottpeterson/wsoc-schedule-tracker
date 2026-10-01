#!/bin/bash
# Hourly entry point for launchd on the Mac.
# With a remote: the GitHub Actions workflow does the checking and committing, so this
# job only pulls the latest state and raises a macOS notification for new change events.
# Without a remote (local-only use): check, build, notify here.
set -u
cd "$(dirname "$0")" || exit 1
PY=/opt/homebrew/bin/python3
if git rev-parse --is-inside-work-tree >/dev/null 2>&1 && git remote get-url origin >/dev/null 2>&1; then
  # Fast-forward to the cloud's latest commit. Never discards local commits that
  # have not been pushed yet; if the branches have diverged, leave it for a human.
  git pull -q --rebase origin main || { git rebase --abort 2>/dev/null; echo "[$(date '+%F %T')] pull failed, notifying from local state"; }
else
  $PY check_schedules.py
  $PY build_site.py
fi
$PY notify_new_events.py
