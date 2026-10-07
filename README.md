# schiphol-max

Forecasts the highest temperature of the Amsterdam day at Schiphol as the most likely whole degree Celsius
and the two degrees either side, each with an honest probability. It runs the evening before and at
06:00, 09:00, 12:00 and 15:00 Amsterdam time on the day, and learns from every miss.

- **Latest forecast:** [FORECAST.md](FORECAST.md)
- **Spec:** [docs/PRD.md](docs/PRD.md) · **Build plan:** [docs/PLAN.md](docs/PLAN.md)
- **Milestone checks and pass criteria:** [reports/checks/](reports/checks/)

## How it runs

There is no server. GitHub Actions runs `smax tick` every hour (`.github/workflows/tick.yml`). Each run:

1. collects whatever is new: model runs (Open-Meteo Single Runs archive), airport reports (NOAA AWC, IEM),
   KNMI daily data, DWD MOSMIX, the ECMWF ensemble, and when each model run was published;
2. rebuilds the derived SQLite database from the raw store (cached between runs, never committed);
3. runs every slot that is due, catching up anything missed in the last 72 hours: weekly refit, forecasts, settling;
4. writes the daily completeness report, the weekly scorecard and `FORECAST.md`;
5. commits everything it produced. A failed job or an alert fails the run, and GitHub emails the owner.

A late run produces exactly the same forecast as an on-time one. Each value's availability comes from its
source (model publish times, airport-report receipt times), never from when it was fetched, and `access.py`
filters every query by the issue time.

## The one daily chore

Weather Underground's terms forbid automated reading, so the target is typed in. Each morning, or weekly,
open <https://www.wunderground.com/history/daily/nl/schiphol/EHAM> with units set to °C, then enter the day's
maximum:

- **GitHub:** Actions → **enter-wu-value** → Run workflow (works in the GitHub phone app), or
- **command line:** `uv run smax target set 2026-10-08 17`

The first value entered for a day is final. Values more than 2 °C from the airport-report maximum need a
confirmation. A reminder alert fires after 2 missing days.

## Commands

```
uv sync                      # install (Python 3.12 via uv)
uv run smax tick --dry-run   # what is due now
uv run smax backfill         # one-off history download (A4)
uv run smax rebuild          # ingest raw files into data/schiphol.sqlite
uv run smax replay           # walk-forward backtest; extends the official record chain in data/
uv run smax replay --dir data/backtests/mlpol --set blend.method=mlpol --variant mlpol
uv run smax score --period test --title "Backtest"
uv run smax compare data data/backtests/mlpol --period tuning
uv run smax reproduce 2026-09-01 2026-09-30     # criterion 9
uv run smax lookahead --n 6                     # criterion 3
uv run smax baselines                            # criterion 2
uv run smax target sheet | check FILE | knmi     # criterion 1 tools
uv run smax errortable                           # C1–C3
uv run smax checks                               # rewrite reports/checks/
uv run pytest
```

## Layout

```
config.yaml           models, schedule, coordinates, tuning values, upgrade dates
data/raw/             append-only fetched responses, by source and date (gzipped JSON)
data/records/         write-once forecast and outcome records
data/params/          write-once fitted parameter sets, each with the moment it takes effect
data/logs/, data/state/  job log lines; consecutive-failure counters
src/schiphol_max/     collect/, access.py, target.py, baselines.py, reduce.py, correct.py, blend.py,
                      calibrate.py, sameday.py, deviation.py, learn.py, params.py, engine.py, live.py,
                      backtest via engine.replay, score.py, errortable.py, reproduce.py, lookahead.py
reports/              error table, scorecards, completeness reports, milestone checks, decisions log
```

## Secrets (optional, GitHub → Settings → Secrets → Actions)

- `HEALTHCHECKS_URL`: a healthchecks.io ping URL. It gets a heartbeat every hour and a `/fail` with the alert text, so it also catches runs that never start.
- `KNMI_API_KEY`: a KNMI Data Platform key. Only needed after KNMI closes its script download at the end of 2026; the KNMI maximum is a reference series only.

## Data and attribution

Weather data by Open-Meteo.com (CC BY 4.0), with model data from ECMWF, DWD, KNMI, NOAA, the UK Met Office
and Météo-France. Observations from KNMI, NOAA Aviation Weather Center and Iowa Environmental Mesonet.
MOSMIX by DWD (CC BY 4.0). Use is personal and non-commercial (Open-Meteo free tier, Weather Underground
terms). Revisit before any commercial use.
