# Plan: build the Schiphol daily-high forecaster

## Context
The project folder contains only the PRD (`Amsterdam daily high forecaster PRD.md`, 4 Oct 2026). Nothing has been built yet.
The PRD already fixes what to build, the milestones (M0–M10) and the 11 pass criteria. This plan covers:
- how I build it, and in what order;
- what today's checks of the live data sources changed;
- what I need from Bernie.

Bernie asked for **no always-on laptop or server**, and that turns out to be possible (see below).

## Bottom line
- **No machine to run.** GitHub's free scheduler runs the system about once an hour, for about a minute each time. All data and records live in a private GitHub repository. **Cost: $0.**
- **Timing:** collection starts about 1 day after approval. Every milestone is built and checked by early November, then comes the PRD's 60-day live soak, so **V1 sign-off is around mid-January 2027**.
- **Forecast delivery:** forecasts arrive about 5–20 minutes after their scheduled hour. The data cut-off is still the scheduled hour.
- **Bernie's time:**
  - 5 minutes of setup;
  - about 30 minutes, once, for the Weather Underground (WU) sample check;
  - about 10 minutes per milestone sign-off;
  - under 1 minute a day to type yesterday's WU maximum into a GitHub form (it works from the phone), or one weekly batch.

## Why no always-on machine is needed
- **The archives already keep the inputs.** Open-Meteo now archives every model run (one every 3 hours), and IEM and KNMI archive the observations. Nothing has to be caught as it happens.
  - Each scheduled run fetches what it needs, saves exactly what it used, and stops.
  - The two sources that only keep data briefly are fetched at every run, so nothing is missed: DWD MOSMIX (about 2 days) and the ensembles (about 3 days).
- **A late run gives the same forecast.** Each value's availability time comes from the source, never from when we happened to fetch it:
  - for model runs, Open-Meteo's own publish time, or the run's start time plus its usual publishing delay;
  - for airport reports, the time the report was received.

  So a job that starts 15 minutes late produces exactly the same forecast, and the no-look-ahead rule still holds.
- **What we give up:**
  - GitHub's scheduler is best-effort. Runs start a few minutes late, and occasionally one is skipped; the next run fills it in and flags it.
  - We lose the 16 hourly HARMONIE runs a day that Open-Meteo's archive drops. Version 1 doesn't use them.

## Decisions made (Bernie, 5 Oct)
1. **Use is personal and non-commercial**, so Open-Meteo's free tier applies. Any trading or company use later means switching to Open-Meteo Professional first. That costs about $99/month and is a one-line config change.
2. **No always-on machine.** The system runs on GitHub Actions' free scheduler, from the private repository `schiphol-max` on the GitHub account **BernieDominik**, which is the one logged in on this Mac. Say if it should be `berniestefko` instead.

## What today's checks changed versus the PRD
1. **Time zones.** Open-Meteo applies the UTC offset in force on the day of the request to the whole date range. The PRD's rule to request `timezone=Europe/Amsterdam` would therefore shift every winter day by an hour. Instead I request UTC and build Amsterdam days myself with `zoneinfo`. Airport reports are requested in UTC too.
2. **Archive depth differs by model.** The day-ahead archive (Previous Runs) starts at different dates:

   | Model | Day-ahead archive starts |
   | --- | --- |
   | GFS | Mar 2021 |
   | ICON-D2, ICON-EU, ARPEGE | Jan 2024 |
   | HARMONIE | Jun 2024 |
   | UKMO | Aug 2024 (patchy until Jul 2025) |
   | AIFS | Feb 2025 |
   | European 9 km model | Oct 2025 |

   The exact-run archive (Single Runs) has the European 9 km model from 14 Mar 2024 and every other model from 2 Apr 2026. It keeps one run every 3 hours. The anchor model therefore trains on exact runs from Mar 2024.
3. **Hidden look-ahead in the day-ahead archive.** For each hour, the "1 day before" value comes from the newest run that started at least 24 hours earlier. For late hours of the target day, that run came out after 21:00.
   - I use, hour by hour, only runs that were out at the issue time.
   - Consequence: HARMONIE and ICON-D2 can only be replayed honestly from April 2026. The backtest mostly measures the global models; the regional models prove themselves in live running.
4. **ICON-D2 covers Schiphol**, so I keep it (PRD open question 7).
5. **MOSMIX maximum (PRD open question 8).** `TX` at 18 UTC covers 06–18 UTC. For the full day, take the higher of `TX` and the hourly `TTT` values outside that window.
6. **KNMI's script download closes at the end of 2026**, during the soak. I pull the full history (1951 onward) now and move the daily feed to the KNMI Data Platform in M0.
7. **IEM airport-report traps.**
   - IEM labels half of Schiphol's reports "specials", so both report types must be requested.
   - Genuine half-hourly reports exist only from about 2012, so the target history starts in 2012.
8. **opera is R-only.** It has been archived on CRAN, and its Python port has no licence. For E3 I write its default method in NumPy, and only when M9 is reached.
9. **Weather Underground's terms forbid automated reading** without written permission. The daily value is therefore typed in by hand, which is the PRD's own fallback.

## Changes to the PRD (approve with this plan)
- **A1/A2, hourly collection.** Replaced by: each scheduled run saves exactly what it used, and the archives hold the rest.
- **"Runs on a Mac or small server"** becomes "runs on GitHub's scheduler".
- **Issue times stay as they are.** Forecasts are delivered 5–20 minutes after them.
- **Working during calendar-only waits.** While waiting on a check that only needs time to pass (the 7 days in M0 and in M7), I build the next milestone. I don't switch it on or sign it off until the earlier check passes.
- **M9 runs during the soak, in backtest only.** Any refinements that win ship after V1 sign-off, so the soak measures one fixed version. This saves about 2 weeks.
- **No tuning on the test year.** I tune only on the year before it, and every run on the test year is logged.

## What I need from Bernie
1. **The OK to create the private repository** `schiphol-max`. I do it with the `gh` command-line tool.
2. **Optional: a free healthchecks.io account** (5 minutes). It alerts you if GitHub silently stops running the jobs. GitHub itself already emails you when a run fails.
3. **The 60-row WU check sheet** (about 30 minutes, can be delegated). It arrives at the start of M1. Each row has a date, a link and a blank to fill in.
4. **Sign-offs and daily values.**
   - One sign-off per milestone, from a one-page check report.
   - Yesterday's WU maximum, entered through a GitHub "Run workflow" form (date and °C) that works in the GitHub phone app, either daily or as a weekly batch. A reminder goes out after 2 missing days.

## How it is built
Python 3.12 via uv, with a pinned lockfile. The layout follows the PRD, as the repository `schiphol-max/`, with the modules inside a `src/schiphol_max/` package. All tuning values live in `config.yaml`. The config keeps two separate model lists, so dropping a model from the blend never stops it being collected.

**Stores, all in the repository and all write-once**
- `data/raw/`: every input a run used, every hand-entered WU value, and the one-off history download.
  - Plain JSON, created with exclusive create.
  - About 65 MB a year, plus about 100 MB of history.
- `data/params/`: every fitted parameter set, with its effective timestamp and a hash (I4).
- `data/records/`: every forecast record and every outcome record.

Two rules apply across the stores:
- `data/schiphol.sqlite` is derived only: it is not committed, and `smax rebuild` recreates it.
- A job counts as done when its output file exists, so every job is safe to run twice.

**Collection, run inside each scheduled job**
- **Model runs.** The newest available run of each model, from the Single Runs API, in UTC, 8 days ahead. Variables: temperature plus a few extras kept for later add-ons.
- **Model publish times.** Each hourly run also records every model's `latest.json` and `meta.json`, which give run times and publish times. Over time this measures every model's publishing delay without any always-on polling.
- **Airport reports.** From aviationweather.gov, which gives receipt times, at each run. IEM serves as the archive of record, read at settle time.
- **Other sources:**
  - MOSMIX: at every run;
  - KNMI daily maximum: once a day;
  - ECMWF ensemble: once a day, kept for later add-ons.
- **One-off history download.** It runs from this Mac, because it would use about one day of free quota. It is committed once.

**Availability: the no-look-ahead rule enforced in code**
- Every stored value carries `available_at`, the moment the source published it:
  - model runs: Open-Meteo's own publish time where we recorded it; otherwise the run's start time plus its 95th-percentile publishing delay;
  - airport reports: their receipt time.
- `access.py` is the only way to read data. It returns nothing that was available after the issue time.
- Live running and the backtest use exactly the same rule.

**Schedule**
- A GitHub workflow runs hourly at :07 UTC, which avoids GitHub's busy top of the hour. Runs never overlap.
- Each run calls `smax tick`, which does whatever is due in Europe/Amsterdam time, including any slot missed earlier:

  | Job | When |
  | --- | --- |
  | Forecast | 21:00, 06:00, 09:00, 12:00, 15:00 |
  | Settle | 01:00, then every hour until the WU value is in |
  | Refit | Sunday 04:00 |
  | Completeness check | 07:00 daily |
  | Scorecard | Monday 08:00 |

- Nothing is scheduled between 02:00 and 03:00, the clock-change hour.
- A forecast produced up to 30 minutes after its issue time counts as on time. Later ones are still written, as of the issue time, and flagged late. Each run commits its outputs.

**The backtest runs the live code**
- The backtest loops over the same scheduled slots across history.
- It calls the same forecast, settle and refit functions through `access.py`, and writes to `data/backtests/<id>/`. The backtest runs on this Mac.
- The replay starts at the beginning of the archive; only the last 12 months are scored.

**Reproducibility**
- Official records come only from the GitHub job, which runs on a pinned runner image, with pinned Python and a pinned lockfile, from a clean commit whose SHA covers `config.yaml`.
- Re-runs load the stored parameters and never refit.
- A nightly step re-runs yesterday's records and fails loudly on any difference.

**Reading the forecast.** `FORECAST.md` at the top of the repository is rewritten by every run and shows the PRD's printed summary. Push notifications to your phone through ntfy are optional and free.

**Alerts**
- GitHub emails you on any failed run.
- The optional healthchecks.io heartbeat catches runs that never start.
- The run itself fails, and so triggers an alert, when:
  - any source fails twice in a row (A6);
  - a WU value has been missing for 2 days;
  - a WU entry is more than 2 °C from the value rebuilt from airport reports. That catches typos and Fahrenheit, and the entry must then be confirmed.

## Build sequence

| M | What I build | Check before moving on (Bernie signs off) | Earliest |
| --- | --- | --- | --- |
| 0 | Repository; GitHub workflow; `tick`; raw store; collectors; publish-time log; completeness report; alerts; WU entry form | 7 days in which every slot ran within 30 minutes, inputs were saved and the completeness report was clean; lateness measured | live ~7 Oct, check ~14 Oct |
| 1 | IEM history 2012→now; `target.py` (whole °C read from the report text, both report types, the Amsterdam day, clock-change days); target vs KNMI by month; WU check sheet (15 days per season, at least 10 days with an early or late maximum) | Criterion 1 (at least 57 of 60) | ~14 Oct |
| 2 | `baselines.py`; KNMI history 1951→now; criterion-2 script (fit 1971–2015, test 2016–2025) | Criterion 2 | ~12 Oct |
| 3 | History download (Single Runs plus Previous Runs, resumable, run from this Mac); hour-by-hour availability map; `reduce.py`; `access.py`; error table as CSV and chart (C1–C3) | Bernie decides which models stay, from my one-line recommendation per model | ~16 Oct |
| 4 | `params.py`; `correct.py`; `backtest.py`; the look-ahead test | Criterion 3; each corrected model beats its own raw forecast | ~19 Oct |
| 5 | `blend.py`, with the core of F1–F2 brought forward so the log-score half of criterion 4 can be checked | Criteria 4 and 5 | ~20 Oct |
| 6 | `calibrate.py`; `deviation.py`; `record.py` (the PRD's JSON, the printed summary, `FORECAST.md`); `score.py` (all metrics, calibration bands, a whole-week bootstrap); `reproduce.py` | Criteria 6, 7, 9 and 11 | ~23 Oct |
| 7 | `learn.py`; the evening, settle, refit and scorecard jobs switched on; nightly re-run | 7 days of live records identical to a re-run | live ~24 Oct, check ~31 Oct |
| 8 | `sameday.py`; same-day backtest; the 06:00, 09:00, 12:00 and 15:00 runs switched on | Criterion 8 | ~3 Nov |
| 9 | E3, F5 and F6, each tested alone against the current best, in backtest during the soak; `reports/decisions.md` | A written keep or drop for each | during the soak |
| 10 | 60-day live soak; final scorecard comparing live with backtest | Criterion 10, plus all 11 criteria in one report | ~early Jan 2027 |

Each milestone ends with `reports/checks/M<n>.md`. It states the pass mark, the measured number, the command that produced it, and the sample sizes.

## PRD ambiguities: my defaults
- **`probabilities` field.** I list every degree within 8 °C of mu, to 4 decimals, rounded so the list sums to exactly 1. The 0.005 cut-off applies only to the printed summary.
- **The spread, sigma (F1).**
  - It comes only from out-of-sample errors in the walk-forward backtest, measured about zero.
  - With fewer than 60 errors, seasons are pooled; if that is still too few, the anchor model's own errors are used.
  - Every model is scored in the background from its first fit, so it already has 60 days of weight history when D4 admits it to the blend.
- **The D1 correction.**
  - I fit the target minus the raw forecast. The regularisation then pulls toward trusting the model, not toward the average, which protects hot days.
  - The seasonal pair is added only once 365 days of history exist.
- **Coverage.** A model counts only if its newest available run covers the whole target day (day-ahead) or the rest of the day (same-day). A maximum over part of the day is never used.
- **Same-day runs (G).**
  - A model's raw forecast is the higher of the observed maximum so far and the model's maximum over the rest of the day.
  - G2's "corrected hourly" value is the raw hourly value plus the model's current correction for the daily maximum.
  - G5 rescales proportionally, as the PRD says. Moving the probability onto the maximum so far is tested as an alternative, judged by log score.
- **Persistence at 21:00** uses the highest airport report so far that day. Criterion 2 uses the classic full-day version on KNMI data.
- **Late or corrected WU values.** Days are settled in date order whenever the values arrive. Running bias, weights and spread are recomputed by replaying outcomes in date order, so arrival order cannot change results.
- **The standard forecast** averages the models in tenths of a degree and rounds half up. Probabilities use the unrounded mu.
- **Extra record fields.** Each record also stores the season and the change in mu since the previous run (H4). Baselines are logged at every live run (B4).
- **Attribution.** Reports credit Open-Meteo (CC BY 4.0), KNMI and DWD.

## Verification
`uv run pytest` must pass locally and in the GitHub workflow before any change goes live. The tests that matter most:
1. **Look-ahead (criterion 3).**
   - Pick random cut-offs, including ±1 second, the clock-change days, and moments just after a refit or settle.
   - Change, delete and insert everything that became available after the cut-off, then re-run, including fits.
   - Earlier records must stay byte-identical.
   - Control check: changing data from before the cut-off must change the output.
2. **A late run gives the same forecast.** Running a slot 5 minutes late and 3 hours late must produce byte-identical records.
3. **Archive versus live.**
   - Check the Previous Runs hour-to-run mapping against Single Runs.
   - Measure, by season, how much error the mixed-run reconstruction adds.
4. **Calendar.** 25 Oct 2026 (25 hours), 28 Mar 2027 (23 hours) and a January day all come out right, and every slot fires exactly once, including the catch-up of missed slots.
5. **Learning.** Parameters come out identical when WU values arrive shuffled, late or corrected.
6. **Probabilities** (property tests).
   - The probabilities sum to 1.
   - The table always has 5 degrees in ascending order.
   - `outside_table` is right.
   - The floors (F4) and G5 are applied.
   - Ties are handled.
7. **Reproduction (criterion 9).** Runs nightly in the workflow, and once over the full backtest.

End to end:
- `smax tick --now <time> --dry-run` on this Mac shows what would run at any moment.
- On GitHub, check the Actions run history (the share of runs on time), the 07:00 completeness report, and that `FORECAST.md` updates after each forecast hour.

## Risks
- **GitHub's scheduler is best-effort.** M0 measures how late runs start. If too many land more than 30 minutes late for criterion 10, the fix is Google Cloud Scheduler: about €1/month at most, on time to the minute, and the same code.
- **GitHub's machines share internet addresses**, so Open-Meteo's per-address limits could occasionally bite. Retries handle it, and the big history download runs from this Mac.
- **Open-Meteo's archive is a free service with no guarantee.** Every run saves what it used, and the history download stays in the repository.
- **Regional models join the backtest late** (see change 3). The backtest probably understates live skill; the soak scorecard will show by how much.
- **Same-day history is thin**, because most exact runs only start in April 2026. Criterion 8 will be measured mainly on the European model, and the report says so.
- **The 21:00 evening run.** The publish-time log shows whether a later time would catch a fresher European run. I report what it would gain (PRD open question 4).
- **Hand-entered WU values** are a single point of failure for learning, though not for forecasting. Mitigated by the reminder and catch-up settling.
- **The non-commercial status covers both Open-Meteo and WU.** Revisit it before any trading or company use.
