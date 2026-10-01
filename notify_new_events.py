#!/opt/homebrew/bin/python3
"""
Send one macOS notification per change event in changes.jsonl that has not
been announced on this machine yet. Works no matter which runner (this Mac
or GitHub Actions) detected the change, because run_hourly.sh pulls the repo
before calling this. Progress is kept in .notified_through (untracked).
"""

import json
import shutil
import subprocess
from pathlib import Path

BASE = Path(__file__).resolve().parent
EVENTS = BASE / "changes.jsonl"
MARKER = BASE / ".notified_through"


def notify(message, title):
    if shutil.which("osascript") is None:
        return
    def esc(text):
        return text.replace("\\", "\\\\").replace('"', '\\"')
    subprocess.run(["osascript", "-e", f'display notification "{esc(message)}" with title "{esc(title)}"'], check=False)


def describe(event):
    kind = event["type"]
    key = event.get("key", "").replace(" | ", ", ")
    if kind == "changed":
        return f"{key}: now {event['new'].split(' | ')[-1]}"
    if kind == "record":
        return "published record changed: " + "; ".join(event["new"][:1])
    if kind in ("added", "removed"):
        return f"game {kind}: {key}"
    if kind == "details":
        return f"expanded details changed: {key}"
    return kind


def main():
    if not EVENTS.exists():
        return
    lines = [line for line in EVENTS.read_text().splitlines() if line.strip()]
    done = int(MARKER.read_text().strip() or 0) if MARKER.exists() else 0
    if done == 0:
        MARKER.write_text(str(len(lines)))  # first run: do not replay history
        return
    for line in lines[done:]:
        event = json.loads(line)
        if event["type"] == "baseline":
            continue
        notify(describe(event)[:220], f"{event['school']} women's soccer schedule changed")
        print(f"notified: {event['school']} {describe(event)}")
    MARKER.write_text(str(len(lines)))


if __name__ == "__main__":
    main()
