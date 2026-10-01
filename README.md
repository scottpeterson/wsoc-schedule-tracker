# Women's soccer schedule tracker

Watches the women's soccer schedule pages of North Central (IL) and UChicago
every hour and reports any change: status labels (Postponed, Canceled,
Forfeit), results, times, locations, added or removed games, and the
published record. Built on 2026-10-01 after the September 30 game between
the two schools was not played and each school listed it differently.

## Layout

| Path | Purpose |
|------|---------|
| `schools.json` | Schools to watch: slug, name, schedule page URL, plain-text feed URL |
| `check_schedules.py` | Fetches, parses, diffs against `snapshots/`, logs changes, sends a macOS notification |
| `build_site.py` | Renders `site/index.html` from the snapshots, `changes.jsonl`, `manual_sources.json`, and `content/story.html` |
| `changes.jsonl` | One JSON object per change, written by `check_schedules.py`, read by `build_site.py` |
| `manual_sources.json` | Sources checked by hand (the NCAA scoreboard), shown as cards on the site |
| `site/assets/` | Team logos copied from `~/projects/d3-bball-npi/myapp/data/logos/`; colors in `schools.json` come from `team_colors.json` there |
| `run_hourly.sh` | What launchd runs: check, build, and push `site/` when it is a git repo with a remote |
| `snapshots/<slug>.json` | Current normalized schedule per school |
| `history/` | Previous snapshot archived each time a change is detected |
| `changes.log` | Append-only human-readable record of every change (and the baselines) |
| `latest_changes.md` | The most recent change report |
| `logs/tracker.log`, `logs/tracker.err` | launchd stdout and stderr |
| `state.json` | Fetch-failure state so a dead site notifies once, not hourly |

Standard library only. Runs with `/opt/homebrew/bin/python3`. Lives under
`~/projects` on purpose: launchd cannot execute scripts under `~/Documents`
or `~/Desktop` without a Full Disk Access grant.

## Schedule

`~/Library/LaunchAgents/com.scottpeterson.wsoc-schedule-tracker.plist`,
`StartInterval` 3600 and `RunAtLoad`. launchd only runs it while the Mac is
awake; a missed interval runs once on wake.

```bash
# status
launchctl print gui/$(id -u)/com.scottpeterson.wsoc-schedule-tracker | grep -E "state|last exit|runs"
# run now
launchctl kickstart -k gui/$(id -u)/com.scottpeterson.wsoc-schedule-tracker
# stop / start
launchctl bootout gui/$(id -u)/com.scottpeterson.wsoc-schedule-tracker
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.scottpeterson.wsoc-schedule-tracker.plist
```

## NCAA scoreboard

`stats.ncaa.org` lists the game as Canceled (Division III women's soccer
scoreboard for 09/30/2026, contest 6585313). The site serves an Akamai bot
challenge to scripted requests, so the hourly job does not fetch it; update
`manual_sources.json` by hand after checking it in a browser. The public
`ncaa.com` scoreboard API returns at most 100 games per day and does not
include canceled games, so it cannot stand in for it.

## Adding a school

Open the school's Sidearm schedule page, copy the **Text** link
(`/services/schedule_txt.ashx?schedule=<id>`), and add an entry to
`schools.json`. The next run saves a baseline and starts diffing.

## Publishing the site (GitHub Pages)

1. Create an empty public GitHub repo, for example `kerfuffle-site`.
2. `cd site && git init -b main && git remote add origin git@github.com:<you>/kerfuffle-site.git`
3. `echo www.chicagoandnorthcentralkerfuffle.com > CNAME` (only once the domain exists).
4. `git add -A && git commit -m "Initial site" && git push -u origin main`
5. Repo Settings, Pages: deploy from branch `main`, folder `/`. Add the custom domain and enable HTTPS.
6. At the registrar, add a CNAME record for `www` pointing to `<you>.github.io`, and the four GitHub Pages A records for the apex.

From then on `run_hourly.sh` commits and pushes `site/` whenever the page changed.
