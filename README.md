# Women's soccer schedule tracker

The tracker checks the women's soccer schedule pages of North Central (IL) and UChicago
twice a day and reports every change. A change is a status label (Postponed, Canceled, Forfeit), a result, a time, a location, an added or removed game, or the published record. I built it on 2026-10-01 after the two schools did not play their September 30 game and then listed it differently.

## Layout

| Path | Purpose |
|------|---------|
| `schools.json` | Schools to watch: slug, name, schedule page URL, text feed URL. The text feed is the plain-text schedule behind the **Text** link on a Sidearm schedule page |
| `check_schedules.py` | Fetches, parses, diffs against `snapshots/`, logs changes, sends a macOS notification |
| `build_site.py` | Renders `docs/index.html` from the snapshots, `changes.jsonl`, `manual_sources.json`, and `content/story.html` |
| `changes.jsonl` | One JSON object per change, written by `check_schedules.py`, read by `build_site.py` |
| `manual_sources.json` | Sources checked by hand (the NCAA scoreboard), shown as cards on the site |
| `docs/assets/` | Team logos copied from `~/projects/d3-bball-npi/myapp/data/logos/`. Colors in `schools.json` come from `team_colors.json` there |
| `run_hourly.sh` | The script launchd runs on the Mac. When the GitHub remote exists, it only pulls and notifies. GitHub Actions does the checking |
| `notify_new_events.py` | macOS notification for each new event in `changes.jsonl`, whichever runner found it |
| `.github/workflows/track.yml` | Twice-daily cloud run: check, build, commit back to `main`. Pages redeploys from `docs/` |
| `snapshots/<slug>.json` | Current normalized schedule per school |
| `history/` | Previous snapshots. The tracker archives one each time it detects a change |
| `changes.log` | Append-only, human-readable log of every change and every baseline |
| `latest_changes.md` | The most recent change report |
| `logs/tracker.log`, `logs/tracker.err` | launchd stdout and stderr |
| `state.json` | Fetch-failure state, so a dead site triggers one notification instead of one per run |

The scripts use the standard library only and run with `/opt/homebrew/bin/python3`. The repo lives under
`~/projects` because launchd cannot run scripts under `~/Documents`
or `~/Desktop` without a Full Disk Access grant.

## Where things run

GitHub Actions runs `check_schedules.py` and `build_site.py` twice a day, at 00:17 and 12:17 UTC (changed from hourly on 2026-10-03). It commits `snapshots/`, `changes.jsonl`, `changes.log`, and `docs/` back to `main`. GitHub Pages serves `docs/`. When the remote exists, the launchd job on the Mac only pulls and notifies. It does not check or commit, so two writers never race on the same files. To force a GitHub Actions run, use `gh workflow run track.yml`.

## Schedule

The launchd agent is `~/Library/LaunchAgents/com.scottpeterson.wsoc-schedule-tracker.plist`,
with `StartInterval` 3600 and `RunAtLoad`. launchd runs it only while the Mac is awake. If the Mac missed an interval, launchd runs the job once on wake.

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
scoreboard for 2026-09-30, contest 6585313). The site serves an Akamai bot
challenge to scripted requests, so the scheduled run does not fetch it. After you check it in a browser, update `manual_sources.json` by hand. The public
`ncaa.com` scoreboard API returns at most 100 games per day and omits
canceled games, so it cannot replace `stats.ncaa.org`.

## Adding a school

1. Open the school's Sidearm schedule page.
2. Copy the **Text** link (`/services/schedule_txt.ashx?schedule=<id>`).
3. Add an entry to `schools.json`.

The next run saves a baseline and starts diffing.

## Publishing (done 2026-10-01)

Repo: https://github.com/scottpeterson/wsoc-schedule-tracker. Pages serves
`docs/` from `main`. Custom domain: set `www.chicagoandnorthcentralkerfuffle.com`
in repo Settings, Pages. DNS at the registrar has four A records on the apex: 185.199.108.153, .109.153, .110.153, and .111.153. It also has a CNAME record for `www` that points to `scottpeterson.github.io`. All records are unproxied.
