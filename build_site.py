#!/opt/homebrew/bin/python3
"""
Build site/index.html from the tracker's snapshots, changes.jsonl,
manual_sources.json, and content/story.html. run_hourly.sh runs this after
check_schedules.py.
"""

import html
import json
import re
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path

BASE = Path(__file__).resolve().parent
SNAP_DIR = BASE / "snapshots"
CHANGES_JSONL = BASE / "changes.jsonl"
MANUAL = BASE / "manual_sources.json"
STORY = BASE / "content" / "story.html"
SCHOOLS = json.loads((BASE / "schools.json").read_text())
SITE_DIR = BASE / "docs"
OUT = SITE_DIR / "index.html"
GAME_DATE_TOKEN = "Sep 30 (Wed)"

FIELD_ORDER = ["Date", "Time", "Home or away", "Opponent", "Location", "Status", "Note"]

CSS = """
:root{--bg:#faf7f4;--fg:#1d1d1b;--muted:#5d5d58;--card:#ffffff;--line:#e3dcd7;--link:#1c5d99;--ncaa:#0a4f8f;--c-north_central:#c30202;--c-uchicago:#880000}
@media (prefers-color-scheme:dark){:root{--bg:#161312;--fg:#ecece6;--muted:#a3a39b;--card:#221c1b;--line:#3a302e;--link:#7fb3e6;--ncaa:#6fa8dc;--c-north_central:#ff7a7a;--c-uchicago:#f29b9b}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:17px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif}
main{max-width:900px;margin:0 auto;padding:24px 16px 64px}h1{font-size:2rem;line-height:1.15;margin:.2em 0}h2{margin-top:2em;border-bottom:1px solid var(--line);padding-bottom:.25em}
p.sub{color:var(--muted);margin-bottom:1.5em}a{color:var(--link)}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;overflow:hidden}
.card header{display:flex;align-items:center;gap:12px;padding:12px 16px;color:#fff}
.card header img{width:44px;height:44px;object-fit:contain;background:#fff;border-radius:50%;padding:4px}
.card header .who{font-weight:700;font-size:1.05rem;line-height:1.2}.card header .what{font-size:.85rem;opacity:.9}
.card .body{padding:14px 16px 16px}.status{font-size:1.5rem;font-weight:800;margin:0 0 .5em}
dl{display:grid;grid-template-columns:max-content 1fr;gap:4px 14px;margin:0;font-size:.95rem}dt{color:var(--muted)}dd{margin:0}
.meta{color:var(--muted);font-size:.85rem;margin-top:.9em}
table{border-collapse:collapse;width:100%;margin:.6em 0 1.2em;font-size:.95rem}
th,td{border-bottom:1px solid var(--line);padding:7px 10px;text-align:center;vertical-align:top}th:first-child,td:first-child{text-align:left}
ul{padding-left:1.2em}li{margin:.35em 0}.timeline li{margin:.7em 0}.timeline time{font-weight:600}
.rules h3{margin:1.5em 0 .3em;font-size:1.05rem}blockquote{margin:.6em 0;padding:.5em 1em;border-left:3px solid var(--line);background:var(--card);border-radius:0 8px 8px 0}blockquote p{margin:.4em 0}
.event{margin:1.2em 0}.event h3{margin:0 0 .3em;font-size:1rem}.small{color:var(--muted);font-size:.9rem}
.more{margin-top:3em;padding:16px 18px;border:1px solid var(--line);border-radius:12px;background:var(--card)}.more h2{margin:0 0 .4em;border:0;padding:0;font-size:1.15rem}.more p{margin:0}
footer{margin-top:2em;color:var(--muted);font-size:.9rem;border-top:1px solid var(--line);padding-top:1em}
"""

CITY_RE = re.compile(r"^[A-Z][A-Za-z.' -]+, ([A-Z][a-z]{1,4}\.?|[A-Z]{2})$")
TIME_RE = re.compile(r"^(\d{1,2}(:\d{2})? ?(AM|PM)( ?\(?[A-Z]{2,3}\)?)?|TBA|TBD)$")
STATUS_RE = re.compile(r"(?i)postpone|cancel|forfeit|no contest|suspend|^tba$|^ppd$")
RESULT_RE = re.compile(r"^(W|L|T),?$")
SCORE_RE = re.compile(r"^\d+-\d+(\s*\(.*\))?$")
RANK_RE = re.compile(r"^(#\d+|RV|No\. ?\d+)$")
NOISE_RE = re.compile(r"^(Watch.*|Listen.*|Live Stats|Game Day Program|Tickets)$")


def esc(text):
    return html.escape(str(text), quote=True)


def structure_row(row):
    """Turn a normalized schedule row into labeled fields."""
    tokens = [t.strip() for t in row.split("|") if t.strip() and not NOISE_RE.match(t.strip())]
    fields = {}
    if not tokens:
        return fields
    fields["Date"] = tokens[0]
    rest = tokens[1:]
    if rest and re.match(r"^[A-Z][a-z]{2} \d{1,2} \(", rest[0]):
        fields["Date"] += " to " + rest.pop(0)  # multi-day tournament rows
    if rest and TIME_RE.match(rest[0]):
        fields["Time"] = rest.pop(0)
    marker = next((i for i, t in enumerate(rest) if t in ("vs", "at", "vs.")), None)
    if marker is not None:
        fields["Home or away"] = "Home" if rest[marker].startswith("vs") else "Away"
        rest = rest[marker + 1:]
        if rest and RANK_RE.match(rest[0]):
            fields["Opponent"] = f"{rest.pop(0)} "
        if rest:
            fields["Opponent"] = fields.get("Opponent", "") + rest.pop(0)
    elif rest:
        fields["Opponent"] = rest.pop(0)
    note, location, status = [], [], []
    i = 0
    while i < len(rest):
        token = rest[i]
        if RESULT_RE.match(token) and i + 1 < len(rest) and SCORE_RE.match(rest[i + 1]):
            status.append(f"{token.rstrip(',')} {rest[i + 1]}")
            i += 2
            continue
        if STATUS_RE.search(token) and location:
            status.append(token)  # the result cell comes after the venue
        elif STATUS_RE.search(token) and not location and TIME_RE.match(token):
            status.append(token)
        elif CITY_RE.match(token):
            location.append(token)
        elif location and not status:
            location.append(token)  # venue name follows the city
        else:
            note.append(token)  # promotion or sponsor text sits before the location
        i += 1
    if location:
        fields["Location"] = ", ".join(location)
    if status:
        fields["Status"] = "; ".join(status)
    if note:
        fields["Note"] = "; ".join(note)
    return fields


def load_snapshot(slug):
    path = SNAP_DIR / f"{slug}.json"
    return json.loads(path.read_text()) if path.exists() else None


def game_for(snapshot, prefix=GAME_DATE_TOKEN):
    return next((g for g in snapshot["games"] if g["key"].startswith(prefix)), None)


def fields_html(fields):
    parts = []
    for name in FIELD_ORDER:
        if name in fields:
            parts.append(f"<dt>{esc(name)}</dt><dd>{esc(fields[name])}</dd>")
    return "<dl>" + "".join(parts) + "</dl>"


def school_card(school):
    snap = load_snapshot(school["slug"])
    head = (f'<header style="background:{school["color"]};color:{school["text"]}">'
            f'<img src="{esc(school["logo"])}" alt="{esc(school["name"])} logo">'
            f'<div><div class="who">{esc(school["name"])} {esc(school["mascot"])}</div>'
            f'<div class="what">Official schedule page</div></div></header>')
    if snap is None:
        return f'<div class="card">{head}<div class="body"><p>No snapshot yet.</p></div></div>'
    game = game_for(snap)
    fields = structure_row(game["row"]) if game else {}
    status = fields.get("Status") or ("Listed, no status shown" if game else "Game not listed")
    overall = re.sub(r"\s+", " ", next((r for r in snap["record"] if r.startswith("Overall")), ""))
    checked = datetime.fromisoformat(snap["fetched_at"]).strftime("%Y-%m-%d %H:%M") + " Central"
    return (f'<div class="card">{head}<div class="body">'
            f'<p class="status" style="color:var(--c-{school["slug"]})">{esc(status)}</p>'
            f'{fields_html(fields)}'
            f'<p class="meta">{esc(overall)}<br>Checked {esc(checked)} &middot; <a href="{esc(school["schedule_url"])}">schedule page</a></p>'
            f'</div></div>')


def manual_cards():
    if not MANUAL.exists():
        return ""
    cards = []
    for src in json.loads(MANUAL.read_text()):
        cards.append(
            f'<div class="card"><header style="background:var(--ncaa)">'
            f'<div><div class="who">{esc(src["name"])}</div><div class="what">Official scoreboard</div></div></header>'
            f'<div class="body"><p class="status" style="color:var(--ncaa)">{esc(src["status"])}</p>'
            f'<p style="margin:0 0 .5em">{esc(src["detail"])}</p>'
            f'<p class="meta">Checked {esc(src["checked"])} &middot; <a href="{esc(src["url"])}">scoreboard</a></p>'
            f'</div></div>')
    return "\n".join(cards)


def diff_table(old_fields, new_fields):
    rows = []
    for name in FIELD_ORDER:
        before, after = old_fields.get(name, ""), new_fields.get(name, "")
        if before != after:
            rows.append(f"<tr><td>{esc(name)}</td><td>{esc(before) or '&mdash;'}</td><td>{esc(after) or '&mdash;'}</td></tr>")
    if not rows:
        return "<p class=\"small\">Only expanded details changed.</p>"
    return "<table><thead><tr><th>Field</th><th>Before</th><th>After</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table>"


def record_table(old, new):
    pairs = {}
    for line in old:
        name, _, value = re.sub(r"\s+", " ", line).partition(" ")
        pairs.setdefault(name, ["", ""])[0] = value
    for line in new:
        name, _, value = re.sub(r"\s+", " ", line).partition(" ")
        pairs.setdefault(name, ["", ""])[1] = value
    rows = [f"<tr><td>{esc(k)}</td><td>{esc(v[0])}</td><td>{esc(v[1])}</td></tr>" for k, v in pairs.items() if v[0] != v[1]]
    return "<table><thead><tr><th>Record line</th><th>Before</th><th>After</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table>"


def change_log_html():
    if not CHANGES_JSONL.exists():
        return "<p>No checks recorded yet.</p>"
    events = [json.loads(line) for line in CHANGES_JSONL.read_text().splitlines() if line.strip()]
    if not events:
        return "<p>No checks recorded yet.</p>"
    blocks = []
    for event in reversed(events):
        when = datetime.fromisoformat(event["time"]).strftime("%Y-%m-%d %H:%M") + " Central"
        school = event["school"]
        kind = event["type"]
        if kind == "baseline":
            body = f'<p class="small">Tracking started. {event["games"]} games on the schedule page.</p>'
            title = f"{school}: first snapshot"
        elif kind == "record":
            title = f"{school}: published record changed"
            body = record_table(event["old"], event["new"])
        elif kind == "changed":
            title = f"{school}: game listing changed"
            body = f'<p class="small">{esc(event["key"].replace(" | ", ", "))}</p>' + diff_table(structure_row(event["old"]), structure_row(event["new"]))
        elif kind == "added":
            title = f"{school}: game added"
            body = fields_html(structure_row(event["new"]))
        elif kind == "removed":
            title = f"{school}: game removed"
            body = fields_html(structure_row(event["old"]))
        else:
            title = f"{school}: expanded details changed"
            body = f'<p class="small">{esc(event.get("key", "").replace(" | ", ", "))}</p>'
        blocks.append(f'<div class="event"><h3>{esc(when)} &middot; {esc(title)}</h3>{body}</div>')
    return "\n".join(blocks)


def main():
    SITE_DIR.mkdir(exist_ok=True)
    story = STORY.read_text() if STORY.exists() else ""
    built = datetime.now(ZoneInfo("America/Chicago")).strftime("%Y-%m-%d %H:%M")  # same clock on the Mac and on GitHub runners
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Chicago and North Central Kerfuffle</title>
<meta name="description" content="How UChicago, North Central (IL), and the NCAA list the September 30, 2026 women's soccer game that was not played, updated hourly.">
<link rel="icon" href="assets/uchicago.png">
<style>{CSS}</style></head><body><main>
<h1>The Chicago and North Central Kerfuffle</h1>
<p class="sub">The September 30, 2026 women's soccer game between UChicago and North Central (IL) was not played. UChicago lists it as a forfeit. North Central lists it as postponed. The NCAA lists it as canceled. This page tracks both schools' schedule listings and records every change, updated hourly.</p>
<h2 id="now">Current listings</h2>
<div class="cards">
{chr(10).join(school_card(s) for s in SCHOOLS)}
{manual_cards()}
</div>
{story}
<h2 id="changes">Change log</h2>
<p class="small">Every change to either schedule listing, newest first.</p>
{change_log_html()}
<section class="more">
<h2 id="more">More Division III numbers</h2>
<p>This page is a side project of <a href="https://thed3statlab.com/">The D3 Stat Lab</a>, independent Division III women's basketball analytics: NPI rankings, season simulations with tournament odds, composite ratings, and conference rankings, updated through the season. If the NPI angle in this story interests you, that is where the metric is explained and tracked.</p>
</section>
<footer>Built {esc(built)} Central. Not affiliated with either school, the CCIW, the UAA, or the NCAA. Schedule data comes from the schools' public schedule pages. Quotes come from the linked public posts. Logos belong to their schools.</footer>
</main></body></html>
"""
    OUT.write_text(page)
    print(f"wrote {OUT} ({len(page)} bytes)")


if __name__ == "__main__":
    main()
