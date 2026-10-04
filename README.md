# Women's soccer schedule tracker

Watches the women's soccer schedule pages of North Central (IL) and UChicago
twice a day and reports any change. A change is a status label (Postponed, Canceled, Forfeit), a result, a time, a location, an added or removed game, or the published record. Built on 2026-10-01 after the September 30 game between
the two schools was not played and each school listed it differently.

## Layout

| Path | Purpose |
|------|---------|
| `schools.json` | Schools to watch: slug, name, schedule page URL, plain-text feed URL |
| `check_schedules.py` | Fetches, parses, diffs against `snapshots/`, logs changes, sends a macOS notification |
| `build_site.py` | Renders `site/index.html` from the snapshots, `changes.jsonl`, `manual_sources.json`, and `content/story.html` |
| `changes.jsonl` | One JSON object per change, written by `check_schedules.py`, read by `build_site.py` |
| `manual_sources.json` | Sources checked by hand (the NCAA scoreboard), shown as cards on the site |
| `site/assets/` | Team logos copied from `~/projects/d3-bball-npi/myapp/data/logos/`. Colors in `schools.json` come from `team_colors.json` there |
| `run_hourly.sh` | What launchd runs on the Mac. With the GitHub remote in place it only pulls and notifies. GitHub Actions does the checking |
| `notify_new_events.py` | macOS notification for each new event in `changes.jsonl`, whichever runner found it |
| `.github/workflows/track.yml` | Twice-daily cloud run: check, build, commit back to `main`. Pages redeploys from `docs/` |
| `snapshots/<slug>.json` | Current normalized schedule per school |
| `history/` | Previous snapshot archived each time a change is detected |
| `changes.log` | Append-only human-readable record of every change (and the baselines) |
| `latest_changes.md` | The most recent change report |
| `logs/tracker.log`, `logs/tracker.err` | launchd stdout and stderr |
| `state.json` | Fetch-failure state so a dead site notifies once, not on every run |

Standard library only. Runs with `/opt/homebrew/bin/python3`. Lives under
`~/projects` on purpose: launchd cannot run scripts under `~/Documents`
or `~/Desktop` without a Full Disk Access grant.

## Where things run

GitHub Actions runs `check_schedules.py` and `build_site.py` twice a day, at 00:17 and 12:17 UTC (changed from hourly on 2026-10-03). It commits `snapshots/`, `changes.jsonl`, `changes.log`, and `docs/` back to `main`. GitHub Pages serves `docs/`. When the remote exists, the Mac job only pulls and notifies. It does not check or commit, which avoids two writers racing on the same files. To force a cloud run: `gh workflow run track.yml`.

## Schedule

`~/Library/LaunchAgents/com.scottpeterson.wsoc-schedule-tracker.plist`,
`StartInterval` 3600 and `RunAtLoad`. launchd only runs it while the Mac is awake. A missed interval runs once on wake.

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
challenge to scripted requests, so the scheduled job does not fetch it. After you check it in a browser, update `manual_sources.json` by hand. The public
`ncaa.com` scoreboard API returns at most 100 games per day and does not
include canceled games, so it cannot stand in for it.

## Adding a school

Open the school's Sidearm schedule page, copy the **Text** link
(`/services/schedule_txt.ashx?schedule=<id>`), and add an entry to
`schools.json`. The next run saves a baseline and starts diffing.

## Publishing (done 2026-10-01)

Repo: https://github.com/scottpeterson/wsoc-schedule-tracker. Pages serves
`docs/` from `main`. Custom domain: set `www.chicagoandnorthcentralkerfuffle.com`
in repo Settings, Pages. DNS at the registrar is four A records on the apex (185.199.108.153, .109.153, .110.153, .111.153) and a CNAME record for `www` to `scottpeterson.github.io`, all unproxied.
