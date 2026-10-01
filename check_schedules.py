#!/opt/homebrew/bin/python3
"""
Women's soccer schedule change tracker.

Fetches each school's Sidearm schedule page plus its plain-text schedule
feed, normalizes every game into a row, and compares the result with the
last snapshot. When anything changes it appends the diff to changes.log,
rewrites latest_changes.md, and fires a macOS notification.

Run it by hand:   ./check_schedules.py
Run it hourly:    launchd agent com.scottpeterson.wsoc-schedule-tracker
Add a school:     edit schools.json (slug, name, schedule_url, text_url)

The text feed URL is the "Text" link on any Sidearm schedule page
(/services/schedule_txt.ashx?schedule=<id>). Standard library only, so it
runs with the Homebrew python3 and needs no virtualenv.
"""

import difflib
import html
import json
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
SCHOOLS_FILE = BASE / "schools.json"
SNAP_DIR = BASE / "snapshots"
HIST_DIR = BASE / "history"
CHANGES_LOG = BASE / "changes.log"
LATEST_MD = BASE / "latest_changes.md"
STATE_FILE = BASE / "state.json"
CHANGES_JSONL = BASE / "changes.jsonl"  # one JSON object per change, read by build_site.py

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140.0 Safari/537.36"
)
TIMEOUT_SECONDS = 30

# Tokens that are link labels or UI chrome, not schedule facts.
NOISE_PATTERNS = [
    r"^Recap$", r"^History$", r"^Box ?Score$", r"^Stats$", r"^Live Stats$",
    r"^Photos$", r"^Video$", r"^Audio$", r"^Tickets$", r"^Game Notes$",
    r"^Watch on .*", r"^Listen on .*", r"^Hide/Show Additional Information.*",
    r"^Game Program$", r"^Preview$", r"^Gallery$", r"^Game Files?$",
]
NOISE_RE = re.compile("|".join(NOISE_PATTERNS), re.IGNORECASE)


def log(message):
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{stamp}] {message}", flush=True)


def notify(message, title):
    """macOS notification. A no-op where osascript does not exist (GitHub Actions)."""
    if shutil.which("osascript") is None:
        return
    def esc(text):
        return text.replace("\\", "\\\\").replace('"', '\\"')
    script = f'display notification "{esc(message)}" with title "{esc(title)}"'
    subprocess.run(["osascript", "-e", script], check=False)


def fetch(url):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    last_error = None
    for _attempt in range(2):
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                return response.read().decode("utf-8", errors="replace")
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            last_error = error
    raise RuntimeError(f"fetch failed for {url}: {last_error}")


def strip_tags(fragment):
    text = re.sub(r"<script.*?</script>|<style.*?</style>", "", fragment, flags=re.S)
    text = re.sub(r"<[^>]+>", "|", text)
    text = html.unescape(text)
    tokens = [re.sub(r"\s+", " ", token).strip() for token in text.split("|")]
    return [token for token in tokens if token]


def parse_games(page_html):
    """Return an ordered list of (key, clean_row, full_row) from a Sidearm schedule page."""
    container_match = re.search(
        r'<ul[^>]*class="[^"]*sidearm-schedule-games-container', page_html)
    if container_match:
        page_html = page_html[container_match.start():]
    # Everything after the game list is Knockout templates and the footer.
    for marker in ("Score By Period", "<footer"):
        end = page_html.find(marker)
        if end != -1:
            page_html = page_html[:end]
    parts = re.split(r'(?=<li[^>]*class="sidearm-schedule-game[\s"])', page_html)
    games = []
    for part in parts[1:]:
        tokens = strip_tags(part)
        if not tokens:
            continue
        # Drop duplicate adjacent tokens (Sidearm repeats several labels).
        deduped = []
        for token in tokens:
            if not deduped or deduped[-1] != token:
                deduped.append(token)
        # The summary row ends where Sidearm's expandable details begin.
        cutoff = next((i for i, t in enumerate(deduped)
                       if t.startswith("Hide/Show Additional Information")), len(deduped))
        clean = []
        for token in deduped[:cutoff]:
            if not NOISE_RE.match(token) and token not in clean:
                clean.append(token)
        date_token = next((t for t in clean if re.match(r"^[A-Z][a-z]{2} \d{1,2} \(", t)), None)
        if date_token is None:
            continue
        key = f"{date_token} | {opponent_from(clean)}"
        games.append((key, " | ".join(clean), " | ".join(deduped)))
    return games


def opponent_from(tokens):
    """Opponent name: first real token after the vs/at marker, or the first
    non-date, non-time token for tournament placeholders."""
    skip = re.compile(r"^(#\d+|RV|No\. ?\d+|\*|[A-Z]{2,6})$")
    time_re = re.compile(r"^(\d{1,2}(:\d{2})? ?(AM|PM|a\.m\.|p\.m\.)( ?\(?[A-Z]{2,3}\)?)?|TBA|TBD)$")
    date_re = re.compile(r"^[A-Z][a-z]{2} \d{1,2} \(")
    markers = ("vs", "at", "vs.")
    if any(t in markers for t in tokens):
        start = max(i for i, t in enumerate(tokens) if t in markers) + 1
        candidates = tokens[start:]
    else:
        candidates = tokens
    for token in candidates:
        if token in markers or skip.match(token) or time_re.match(token) or date_re.match(token):
            continue
        return token
    return ""


def parse_text_feed(text):
    lines = [line.rstrip() for line in text.splitlines()]
    record = [line for line in lines if re.match(r"^(Overall|Conference|Streak|Home|Away|Neutral)\s", line)]
    schedule = [line for line in lines if re.match(r"^[A-Z][a-z]{2} \d{1,2} \(", line)]
    return record, schedule


def snapshot_for(school):
    schedule_html = fetch(school["schedule_url"])
    text_feed = fetch(school["text_url"])
    games = parse_games(schedule_html)
    if not games:
        raise RuntimeError(f"parsed zero games from {school['schedule_url']}")
    record, schedule_lines = parse_text_feed(text_feed)
    if not schedule_lines:
        raise RuntimeError(f"parsed zero schedule lines from {school['text_url']}")
    return {
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
        "record": record,
        "text_schedule": schedule_lines,
        "games": [{"key": key, "row": row, "full": full} for key, row, full in games],
    }


def diff_snapshots(old, new):
    """Return a list of human-readable change lines, empty when nothing changed."""
    changes = []
    if old["record"] != new["record"]:
        changes.append("Record block changed:")
        changes.extend(f"    - {line}" for line in old["record"] if line not in new["record"])
        changes.extend(f"    + {line}" for line in new["record"] if line not in old["record"])

    old_games = {g["key"]: g for g in old["games"]}
    new_games = {g["key"]: g for g in new["games"]}
    for key in old_games:
        if key not in new_games:
            changes.append(f"Game removed from schedule page: {old_games[key]['row']}")
    for key in new_games:
        if key not in old_games:
            changes.append(f"Game added to schedule page: {new_games[key]['row']}")
    for key in new_games:
        if key in old_games and old_games[key]["row"] != new_games[key]["row"]:
            changes.append(f"Game changed: {key}")
            changes.append(f"    was: {old_games[key]['row']}")
            changes.append(f"    now: {new_games[key]['row']}")
        elif key in old_games and old_games[key]["full"] != new_games[key]["full"]:
            changes.append(f"Game details (expanded section) changed: {key}")

    if old["text_schedule"] != new["text_schedule"]:
        text_diff = list(difflib.unified_diff(
            old["text_schedule"], new["text_schedule"],
            fromfile="text feed (previous)", tofile="text feed (now)", lineterm="", n=0))
        if text_diff:
            changes.append("Text feed changed:")
            changes.extend(f"    {line}" for line in text_diff[2:])
    return changes


def structured_changes(old, new):
    """Same comparison as diff_snapshots, as records for build_site.py."""
    events = []
    old_games = {g["key"]: g for g in old["games"]}
    new_games = {g["key"]: g for g in new["games"]}
    if old["record"] != new["record"]:
        events.append({"type": "record", "old": old["record"], "new": new["record"]})
    for key, game in old_games.items():
        if key not in new_games:
            events.append({"type": "removed", "key": key, "old": game["row"]})
    for key, game in new_games.items():
        if key not in old_games:
            events.append({"type": "added", "key": key, "new": game["row"]})
        elif old_games[key]["row"] != game["row"]:
            events.append({"type": "changed", "key": key, "old": old_games[key]["row"], "new": game["row"]})
        elif old_games[key]["full"] != game["full"]:
            events.append({"type": "details", "key": key})
    return events


def append_events(slug, name, events):
    stamp = datetime.now().isoformat(timespec="seconds")
    with CHANGES_JSONL.open("a") as handle:
        for event in events:
            handle.write(json.dumps({"time": stamp, "slug": slug, "school": name, **event}) + "\n")


def summarize_for_notification(changes):
    for line in changes:
        if line.startswith("Game changed: "):
            return line[len("Game changed: "):]
    for line in changes:
        if line.startswith("Game ") or line.startswith("Record"):
            return line
    return changes[0] if changes else "schedule changed"


def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"failing": {}}


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2))


def main():
    schools = json.loads(SCHOOLS_FILE.read_text())
    state = load_state()
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    report_sections = []
    any_change = False

    for school in schools:
        slug, name = school["slug"], school["name"]
        snap_path = SNAP_DIR / f"{slug}.json"
        try:
            new = snapshot_for(school)
        except Exception as error:
            log(f"{name}: ERROR {error}")
            if not state["failing"].get(slug):
                notify(f"{name}: {error}"[:200], "WSOC schedule tracker: fetch failed")
            state["failing"][slug] = str(error)
            continue
        if state["failing"].pop(slug, None):
            log(f"{name}: fetch recovered")

        if not snap_path.exists():
            snap_path.write_text(json.dumps(new, indent=2))
            log(f"{name}: baseline saved ({len(new['games'])} games)")
            append_events(slug, name, [{"type": "baseline", "games": len(new["games"]), "record": new["record"]}])
            with CHANGES_LOG.open("a") as handle:
                handle.write(f"\n## {stamp} {name}: baseline saved\n")
                for line in new["record"]:
                    handle.write(f"    {line}\n")
                for game in new["games"]:
                    handle.write(f"    {game['row']}\n")
            continue

        old = json.loads(snap_path.read_text())
        changes = diff_snapshots(old, new)
        if not changes:
            log(f"{name}: no change ({len(new['games'])} games)")
            continue

        any_change = True
        log(f"{name}: {len(changes)} change lines")
        HIST_DIR.mkdir(exist_ok=True)
        archive = HIST_DIR / f"{slug}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        archive.write_text(json.dumps(old, indent=2))
        snap_path.write_text(json.dumps(new, indent=2))
        append_events(slug, name, structured_changes(old, new))

        section = [f"## {stamp} {name}", f"Page: {school['schedule_url']}"] + changes
        report_sections.append(section)
        with CHANGES_LOG.open("a") as handle:
            handle.write("\n" + "\n".join(section) + "\n")

    save_state(state)
    if any_change:
        body = [f"# Latest schedule changes ({stamp})", ""]
        for section in report_sections:
            body.extend(section)
            body.append("")
        LATEST_MD.write_text("\n".join(body))
    return 0


if __name__ == "__main__":
    sys.exit(main())
