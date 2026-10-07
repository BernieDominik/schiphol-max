# Amsterdam daily high forecaster PRD

Oct 4, 2026 · @Bernie

## Summary

This system forecasts the highest temperature of the day at Amsterdam Schiphol, as the most likely whole degree Celsius and the two degrees on either side, each with an honest probability. It runs the evening before and at fixed hours on the day itself.

It does not forecast the weather from scratch. It takes forecasts from several public weather models, corrects each one for its known errors at Schiphol, blends them, and turns the blend into a probability for each whole degree. It then learns from every miss.

Example output: "Tomorrow's maximum: 20 °C (31%). Either side: 18 °C (10%), 19 °C (24%), 21 °C (22%), 22 °C (9%). The standard forecast is more likely to be too low than too high (58% against 42%)."

Version 1 is done when three things are true:

- It produces a logged forecast at every scheduled run for 60 days in a row, with no gaps in data collection.
- Its day-ahead forecast beats every single weather model it uses, measured on data it was not trained on.
- Its stated probabilities match reality: outcomes it rates near 30% happen about 30% of the time.

Realistic expectation, from the research behind this design: a day ahead, the top degree will be right about 3 days in 10. By noon on the day, 5 to 7 days in 10 looks reachable but is untested. No design reaches 90% on a single degree a day ahead. The five listed degrees together should contain the maximum on roughly 9 days in 10; that figure is an estimate.

## Goals and non-goals

The goal is the highest honest probability on a single whole degree, not the highest-looking number.

**Version 1 must:**

1. Name the most likely whole degree Celsius for the daily maximum and list it with the two degrees above and the two below. That gives five degrees every run, each with its own probability.
2. Forecast the evening before and at 06:00, 09:00, 12:00 and 15:00 Amsterdam time on the day, and measure the hit rate at each.
3. Say which way and how far the standard weather models are likely to miss today.
4. Learn from every outcome: update each model's correction and its weight in the blend daily.
5. Log every forecast and every outcome permanently, so high-confidence days can be checked against the record.
6. Run unattended on a schedule, on an Apple-silicon Mac or a small server.

**Version 1 must not:**

- Merge degrees into a range. Each of the five degrees is listed alone with its own probability, and the most likely one is the answer.
- Narrow its spread to make probabilities look higher. A forecast that says 60% and is right 30% of the time is a failure.
- Train its own weather model from raw observations. That was considered and set aside; see Later add-ons.
- Place trades or connect to any market. It produces forecasts only.
- Forecast any location other than Schiphol, or any quantity other than the daily maximum.

## Key terms

These words are used the same way throughout this document and should be used the same way in the code.

| Term | Meaning |
| --- | --- |
| Target | The number being predicted: the Weather Underground daily maximum for Schiphol, in whole degrees Celsius. |
| Target day | The Amsterdam calendar day the forecast is for, midnight to midnight local time. |
| Weather model | A physics or AI forecast system run by a weather centre, such as the European centre's model. Also called an input. |
| Issue time | The moment a forecast is produced. Only data available before this moment may be used. |
| Lead | How far ahead the forecast is. Lead 1 is issued the evening before; lead 0 runs are issued on the target day. |
| Raw forecast | A weather model's own predicted maximum for the target day, before any correction. |
| Bias | A weather model's average error at Schiphol, for example "1.1 °C too cold on summer afternoons". |
| Correction | A small fitted formula that removes a model's bias. One per model and lead. |
| Blend | The weighted average of all corrected models. |
| Weight | How much each corrected model counts in the blend. Weights are learned and change daily. |
| Spread | The width of the uncertainty around the blend, as a standard deviation in °C. |
| Calibration | The property that stated probabilities match observed frequencies. |
| Top degree | The whole degree with the highest probability. This is the system's answer. |
| Five-degree table | The top degree and the two whole degrees on each side, each with its probability. Every run reports this. |
| Hit | A forecast whose top degree equals the target. |
| Standard forecast | The plain average of the raw forecasts, rounded. It stands for what the public sees. |
| Baseline | A deliberately simple forecast used as a yardstick, such as "tomorrow equals today". |
| Backtest | Replaying history as if live, using only data that was available at each issue time. |
| MAE | Mean absolute error: the average size of the miss in °C, ignoring direction. |
| Log score | The average of minus the logarithm of the probability given to what happened. Lower is better. |

## The target

The target is the highest temperature shown on the [Weather Underground history page for Schiphol](https://www.wunderground.com/history/daily/nl/schiphol/EHAM) for the target day, in whole degrees Celsius. Everything is trained and scored on this number and no other.

**Why this needs care.** Three different "daily maximum" values exist for the same date, and they do not always agree.

| Series | Day window | Precision | Role here |
| --- | --- | --- | --- |
| Weather Underground Schiphol | Amsterdam local day | Whole °C | The target |
| Maximum rebuilt from archived airport reports | Amsterdam local day | Whole °C | Stand-in for the target's history |
| Dutch weather service (KNMI) official maximum, station 240 | 00:00 to 24:00 UTC | 0.1 °C | Reference and pipeline check only |

The differences are largest in winter. In the 2015–2025 Schiphol record, about 6% of December and January maxima fell in the last UTC hour, which belongs to the next Amsterdam day. About one day in five had an official maximum ending in .4 or .5, where rounding can go either way.

**Rules for the target value**

1. The target day runs from 00:00 to 24:00 Europe/Amsterdam time. Handle the two clock-change days each year explicitly.
2. The value is final once the first observation of the following day appears on the page. Record it then and never change it afterwards.
3. Store the value as an integer. Never store Fahrenheit.

**Building the history**

The page has no bulk download, so the past is rebuilt from archived airport weather reports for Schiphol (station code EHAM).

1. Download all EHAM reports from the [Iowa Environmental Mesonet archive](https://mesonet.agron.iastate.edu/request/download.phtml?network=NL__ASOS), with timestamps in Europe/Amsterdam time. Use 2004 onward: the station last moved in March 2004.
2. For each local day, take the highest whole-degree temperature across all reports, including special reports between the half-hours.
3. Check the rebuilt series against the Weather Underground page on 60 sample days: 15 per season, with at least 10 days whose maximum came before 09:00 or after 20:00.
4. Pass mark: the two agree on at least 57 of 60 days. If not, find the rule that explains the mismatches before going further.
5. Also store the KNMI official maximum for every day and report how often the rounded value differs from the target, by month.

**Collecting it live**

Record the page's value once a day, after the freeze in rule 2. Before automating that read, check Weather Underground's terms of use. If automated reading is not permitted, enter the value by hand; it takes under a minute a day.

The assumption that the page is built from these airport reports is not confirmed. Step 3 is the test of it.

## Data sources

Everything needed is free. The one thing that cannot be bought back is history, so collection starts on day one and must never have gaps.

All requests use the Schiphol station position: latitude 52.318, longitude 4.790.

**Observations**

| Source | Used for | Access | History | Terms |
| --- | --- | --- | --- | --- |
| [Weather Underground, Schiphol](https://www.wunderground.com/history/daily/nl/schiphol/EHAM) | The target, recorded daily | Web page, one date per view | Any past date can be viewed | Check terms before automating |
| [Iowa Environmental Mesonet, EHAM](https://mesonet.agron.iastate.edu/request/download.phtml?network=NL__ASOS) | Rebuilding the target's history; observations for same-day runs | Download form that produces a CSV link | Archive listed from 1932; use 2004 onward | Public archive |
| [KNMI daily data, station 240](https://www.daggegevens.knmi.nl/klimatologie/daggegevens) | Official maximum (`TX`, in 0.1 °C) and the hour it occurred (`TXH`) | GET with `stns=240`, `vars=TX:TXH`, `start` and `end` as YYYYMMDD | From 1951 | Open data, attribution required |

**Weather-model forecasts**

| Source | Used for | Access | History | Terms |
| --- | --- | --- | --- | --- |
| [Open-Meteo Previous Runs](https://open-meteo.com/en/docs/previous-runs-api) | Past forecasts at leads of 1 to 7 days, per model. The training data for day-ahead forecasts. | `previous-runs-api.open-meteo.com/v1/forecast`; hourly variables `temperature_2m_previous_day1` to `_previous_day7` | Most models from January 2024; the US model from March 2021 | Free tier is non-commercial: 600 calls a minute, 5,000 an hour, 10,000 a day |
| [Open-Meteo Single Runs](https://open-meteo.com/en/docs/single-runs-api) | Each model run exactly as issued. The training data for same-day forecasts. | Request by run start time | European model from 14 March 2024; all others from 2 April 2026 | Same |
| Open-Meteo Forecast and [Ensemble](https://open-meteo.com/en/docs/ensemble-api) | Live forecasts at each run, including the range across ensemble members | Standard forecast request | Ensemble history is only three days deep | Same |
| [DWD MOSMIX, station 06240](https://opendata.dwd.de/weather/local_forecasts/mos/MOSMIX_L/single_stations/06240/kml/) | An outside benchmark: a ready-made corrected forecast for Schiphol | Files on an open server | Latest runs only | German open data |

**Weather models to request in version 1**

| Model | Operator | Grid | Reach | Note |
| --- | --- | --- | --- | --- |
| IFS high resolution | European centre (ECMWF) | 9 km | 15 days | The anchor input |
| AIFS Single | ECMWF | About 30 km | 15 days | AI model; output every 6 hours, so the afternoon peak is not sampled directly |
| HARMONIE-AROME Netherlands | KNMI | 2 km | 60 hours | Runs hourly; archive from mid-2024 |
| ICON-D2 | German service (DWD) | About 2 km | 48 hours | Confirm it returns values for Schiphol; domain coverage is unconfirmed |
| ICON-EU | DWD | 7 km | 5 days |  |
| GFS | US service (NOAA) | 25 km | 16 days | Weakest input, longest archive |
| Global 10 km | UK Met Office | 10 km | 7 days |  |
| ARPEGE Europe | Météo-France | 11 km | 4 days |  |

Three rules for the developer:

- Copy each model's identifier from the request builder on the Open-Meteo documentation page. Do not guess identifiers.
- Always request with `timezone=Europe/Amsterdam` and compute each model's daily maximum from its hourly values over the target day. Do not use Open-Meteo's ready-made daily maximum.
- Do not use Open-Meteo's Historical Forecast API for training. It is stitched from the first hours of each run and cannot show how errors grow with lead.

## How the system works

Each forecast is made in six steps, and a seventh step the next day closes the learning loop.

&#91;embedded content: forecast pipeline · 6 steps and a learning loop\]

The three arrows out of the learning step are the system's memory: each model's bias, each model's weight in the blend, and the spread.

1. **Collect.** Pull the latest run of every weather model and the latest Schiphol observations. Save the raw responses with the time they were fetched.
2. **Reduce.** For each model, compute its maximum over the target day from its hourly values. This is the raw forecast.
3. **Correct.** Apply that model's correction for this lead and time of year.
4. **Blend.** Take the weighted average of the corrected models.
5. **Calibrate.** Put a spread around the blend and convert it into a probability for each whole degree.
6. **Publish and log.** Write the forecast record. Records are never edited afterwards.
7. **Score and learn.** Once the target is final, score every forecast made for that day, then update the corrections, the weights and the spread.

**Daily schedule, Amsterdam time**

| Run | Time | Lead | New information at this run |
| --- | --- | --- | --- |
| Evening | 21:00 the day before | 1 | The afternoon runs of the weather models |
| Early | 06:00 | 0 | Overnight model runs; observations up to 06:00 |
| Morning | 09:00 | 0 | How far each model has been off since midnight |
| Noon | 12:00 | 0 | The maximum so far; the morning's warming rate |
| Afternoon | 15:00 | 0 | The maximum so far, usually close to final in summer |
| Settle | 01:00 the next day | none | The final target; scoring and learning |
| Collect | Every hour | none | Every new model run and observation is saved |

The evening run also produces forecasts for leads 2 to 7 with the same steps. They are logged and scored, but only lead 1 and the same-day runs count toward the version 1 pass criteria.

Each run records which run of each weather model it used. A model run that has not arrived by the issue time is not waited for; the previous run is used and flagged.

## Functional requirements

Each requirement has an ID so it can be ticked off and referenced in code and tests. "Must" items are required for version 1; "should" items are built only after the must items pass.

One rule overrides all others: **no look-ahead.** Anything fitted or computed for a forecast may use only data that existed before its issue time.

### A. Data collection

- **A1 (must).** An hourly job fetches the latest forecast from every weather model in the list and saves the raw response with the fetch time, model name and model run time.
- **A2 (must).** An hourly job fetches the latest Schiphol airport reports. A daily job fetches the KNMI official maximum.
- **A3 (must).** Raw responses are append-only. Nothing is overwritten or deleted. All derived tables can be rebuilt from the raw store.
- **A4 (must).** A one-off backfill loads all available history from the Previous Runs and Single Runs archives and the airport-report archive.
- **A5 (must).** All timestamps are stored in UTC. The target day is derived using the Europe/Amsterdam time zone, never a fixed offset.
- **A6 (must).** A daily completeness check lists every expected fetch that is missing. Two failures in a row for any source raise an alert.

### B. Baselines

- **B1 (must).** Persistence: tomorrow's maximum equals today's.
- **B2 (must).** Climatology: a fitted seasonal curve plus a straight-line warming trend.

```latex
\text{clim}(t) = a + b\,t + \sum_{k=1}^{2}\left[c_k \sin\!\left(\tfrac{2\pi k\,d}{365.25}\right) + e_k \cos\!\left(\tfrac{2\pi k\,d}{365.25}\right)\right]
```

Here t is the date in years and d is the day of the year.

- **B3 (must).** Autoregression: today's departure from climatology, multiplied by one fitted coefficient, added to tomorrow's climatology. The research found a coefficient of about 0.74.
- **B4 (must).** All three baselines are scored at every lead alongside the real forecasts, permanently.

### C. Error table

- **C1 (must).** For every weather model, lead (1 to 7) and season, compute: number of days, bias (forecast minus target), MAE, and how often the rounded raw forecast hit the target.
- **C2 (must).** Output the table as a CSV file and as one chart of MAE against lead with a line per model.
- **C3 (must).** Include the three baselines and MOSMIX as extra rows.

### D. Correction, one per model and lead

- **D1 (must).** Fit a linear regression of the target on the model's raw forecast plus one pair of seasonal terms, with light ridge regularisation.

```latex
\hat{y} = a + b\,x_{\text{raw}} + c \sin\!\left(\tfrac{2\pi d}{365.25}\right) + e \cos\!\left(\tfrac{2\pi d}{365.25}\right)
```

- **D2 (must).** Train on all history before the issue time. Refit weekly.
- **D3 (must).** Add a running bias that follows recent misses, updated daily with weight w = 0.03.

```latex
r_{\text{new}} = (1 - w)\,r_{\text{old}} + w\,(y - \hat{y}), \qquad x_{\text{corrected}} = \hat{y} + r
```

- **D4 (must).** A model enters the blend at a given lead only once it has 180 paired days of history at that lead.
- **D5 (must).** Do not use tree-based learners for this step. They cannot predict above the highest value in their training data, which fails on record-warm days.

### E. Blend

- **E1 (must).** Weight each corrected model by the inverse of its MAE over the last 60 days at that lead. Normalise the weights to sum to 1.
- **E2 (must).** If a model is missing at issue time, renormalise over the models that are present. With fewer than three models, still forecast but flag the record as degraded.
- **E3 (should).** Add online expert aggregation with the [opera](https://github.com/Dralliag/opera) package and squared-error loss. Keep it only if it beats E1 in the backtest.
- **E4 (must).** The blend output is one decimal number in °C, called mu.

### F. Calibration and probabilities

- **F1 (must).** Estimate the spread, sigma, as the standard deviation of past blend errors at the same lead, separately for each season.
- **F2 (must).** Convert mu and sigma into a probability for each whole degree k using a normal distribution with cumulative function F.

```latex
P(k) = F\!\left(k + 0.5\right) - F\!\left(k - 0.5\right)
```

- **F3 (must).** The answer is the degree with the highest probability, called the top degree. Report it with the two degrees above and the two below, each with its own probability. This is the five-degree table.
- **F4 (must).** Give every degree within 8 °C of mu a minimum probability of 0.001, then rescale to sum to 1. This keeps the log score finite.
- **F5 (should).** Replace the normal distribution with a Student-t distribution with fitted tail weight. Keep it only if the log score improves. Practitioners report that normal tails are too thin for this kind of forecast.
- **F6 (should).** Let sigma depend on how much the corrected models disagree today. Keep it only if the log score improves.

* **F7 (must).** Report the probability left outside the five degrees as one extra number. Do not rescale the five to sum to 1; that would overstate each of them.
* **F8 (must).** The table is always the top degree and its four neighbours. This holds in same-day runs too, when degrees below the maximum so far show a probability near zero.

### G. Same-day updates

- **G1 (must).** At each same-day run, compute the maximum so far: the highest airport report since 00:00 local time.
- **G2 (must).** Compute each model's error so far: observed minus corrected hourly temperature, averaged over the last three hours.
- **G3 (must).** Shift mu by a fitted fraction of the error so far. Fit one fraction per issue hour.
- **G4 (must).** Fit sigma separately for each issue hour and season from same-day backtest errors.
- **G5 (must).** Set the probability of every degree below the maximum so far to 0.002 in total, then rescale. Observations are occasionally revised, so it is not exactly zero.
- **G6 (must).** Keep probability above the maximum so far for as long as the data supports it. In November to February a large share of maxima arrive in the evening or at night.

### H. Deviation from the standard forecast

- **H1 (must).** Compute the standard forecast: the plain average of all raw forecasts, rounded to a whole degree.
- **H2 (must).** Report three probabilities from the calibrated distribution: the target lands above, on, or below the standard forecast.
- **H3 (must).** Report the probability that the target differs from the standard forecast by 2 °C or more, next to the average of that figure over the past 365 days.
- **H4 (must).** Log the model disagreement, the season and the change in mu since the previous run with each record.

### I. Learning

- **I1 (must).** At each settle run: record the target, score all forecasts for that day, update every running bias (D3) and every blend weight (E1).
- **I2 (must).** Weekly: refit the regressions (D1) and the spreads (F1, G4).
- **I3 (must).** Keep a dated list of weather-model upgrades in the configuration. For 30 days after an upgrade, raise that model's running-bias weight to 0.10.
- **I4 (must).** Save every fitted parameter with the date it took effect, so any past forecast can be reproduced exactly.

### J. Reporting

- **J1 (must).** Each run writes one forecast record per target day, in the format in the next section.
- **J2 (must).** Each run prints a short summary a person can read.
- **J3 (must).** A weekly scorecard reports the metrics in the testing section, by run and lead.

## Forecast output

Every run writes one record per target day. The record holds the five-degree table, the full distribution behind it, and enough detail to reproduce it later.

```json
{
  "target_day": "2026-10-05",
  "run": "evening",
  "lead": 1,
  "issued_at_utc": "2026-10-04T19:00:00Z",

  "top_degree": 17,
  "top_probability": 0.31,
  "table": [
    {"degree": 15, "probability": 0.10},
    {"degree": 16, "probability": 0.24},
    {"degree": 17, "probability": 0.31},
    {"degree": 18, "probability": 0.21},
    {"degree": 19, "probability": 0.08}
  ],
  "outside_table": 0.06,

  "probabilities": {"13": 0.01, "14": 0.03, "15": 0.10, "16": 0.24,
                    "17": 0.31, "18": 0.21, "19": 0.08, "20": 0.02},
  "mu": 16.9,
  "sigma": 1.28,
  "distribution": "normal",

  "standard_forecast": 16,
  "p_above_standard": 0.62,
  "p_on_standard": 0.24,
  "p_below_standard": 0.14,
  "p_miss_2_or_more": 0.35,
  "p_miss_2_or_more_typical": 0.25,

  "max_so_far": null,
  "model_disagreement": 1.9,
  "models": [
    {"name": "ifs_hres", "run_time_utc": "2026-10-04T12:00:00Z",
     "raw": 15.8, "corrected": 16.7, "weight": 0.21, "stale": false}
  ],
  "degraded": false,
  "parameter_version": "2026-10-01",
  "code_version": "a1b2c3d"
}
```

The numbers above are made up to show the format.

**Rules**

- `probabilities` sums to 1 and lists every degree with a probability of 0.005 or more.
- `max_so_far` is null for lead 1 and later; it is an integer for same-day runs.
- `models` has one entry per weather model used. `stale` is true when the model's newest run had not arrived and an older one was used.
- A record is written once and never changed.

* `table` always has five entries, in ascending order: the top degree and the two whole degrees on each side. `outside_table` is 1 minus their sum.

**The outcome record**

At the settle run, one outcome row is written per forecast record: the target, whether the top degree was a hit, whether the target fell inside the five-degree table, the error (mu minus target), the probability that had been given to the target, and the log score.

**The printed summary**

```
Mon 5 Oct, issued Sun 21:00
  15 °C   10%
  16 °C   24%
  17 °C   31%   most likely
  18 °C   21%
  19 °C    8%
  other    6%
Standard forecast 16 °C: 62% chance the maximum is higher, 14% lower.
Chance of a miss of 2 °C or more against the standard forecast: 35% (typical 25%).
```

## Testing and acceptance

A version of the model is better only if it scores better on days it was not trained on. Every claim in the scorecard must come from the walk-forward backtest or from live running.

**Metrics**

| Metric | What it answers | Better is |
| --- | --- | --- |
| Hit rate | How often is the top degree exactly right? | Higher |
| MAE of mu | How far off is the central estimate, in °C? | Lower |
| Log score | Did the probabilities put weight on what happened? | Lower |
| Calibration table | Do stated probabilities match observed hit rates? | Closer |
| 90% interval coverage | Does the middle 90% of the distribution contain the target 90% of the time? | Closer to 90% |
| Five-degree coverage | How often does the target land inside the five listed degrees? | Closer to the stated total |

**Test protocol**

1. Walk forward one day at a time. For each day, fit on data strictly before the issue time, forecast, store, move on.
2. Use the most recent 12 months of the archive as the test period. Everything earlier is for training only.
3. Report every metric by run, by lead and by season.
4. Report two groups of difficult days separately: days when the target moved 5 °C or more from the previous day, and days at or above 30 °C.
5. Compare any two versions on the same days. Give a 95% interval for the difference in MAE by resampling whole weeks 1,000 times.
6. Build the calibration table from every probability in the five-degree table, not only the top one. Use bands of stated probability: under 10%, 10–20%, 20–30%, 30–40%, 40–50%, above 50%. For each band, compare the average stated probability with how often those degrees were the target.

One year of data cannot separate methods that differ by a tenth of a degree. In the research backtest, the same model's yearly MAE varied by about 0.2 °C between years. If the interval in step 5 includes zero, treat the two versions as equal and keep the simpler one.

**Pass criteria for version 1**

| # | Criterion | Pass mark |
| --- | --- | --- |
| 1 | Rebuilt target matches the Weather Underground page | At least 57 of 60 sample days |
| 2 | Baselines reproduce the research figures on the KNMI official maximum (fit 1971–2015, test 2016–2025, lead 1) | Persistence 2.00, climatology 2.68, autoregression 1.88 °C MAE, each within 0.10 |
| 3 | No look-ahead | Automated test: altering any data dated after an issue time leaves that forecast unchanged |
| 4 | Day-ahead blend beats its inputs | Lower MAE and lower log score than every single corrected model and than the standard forecast |
| 5 | Day-ahead blend beats the baselines | MAE at least 25% below the autoregression baseline |
| 6 | Probabilities are honest | In every band with 100 or more listed probabilities, observed frequency within 5 percentage points of the stated average |
| 7 | Spread is honest | 90% interval coverage between 86% and 94% overall, and between 84% and 96% in each season |
| 8 | Same-day runs are measured | Hit rate, MAE and calibration reported for each of the four issue hours, with sample sizes |
| 9 | Past forecasts can be reproduced | Re-running any stored forecast from raw data and stored parameters gives the identical record |
| 10 | It runs unattended | 60 days in a row with every scheduled run logged and no collection gaps |
| 11 | The five-degree table is honest | Share of days with the target inside the table within 4 percentage points of the average stated total |

For criterion 2: if the figures differ by more than 0.10 °C after careful checking, report the difference. The research figures were computed from a mirror of the KNMI files and could themselves be off.

**What to expect, not pass marks**

These come from studies elsewhere in Europe, not from Schiphol, so they are expectations to be replaced by measurements.

| Run | Expected MAE of mu | Expected hit rate |
| --- | --- | --- |
| Evening, lead 1 | 0.8–1.2 °C | About 30% |
| 06:00 on the day | 0.8–1.0 °C | 31–38% |
| 12:00 on the day | 0.4–0.6 °C | 50–68% |

A lead 1 MAE above 1.4 °C means something is wrong; investigate before continuing.

## Build plan

Build in this order. Collection comes first because every day without it is history lost for good.

| # | Milestone | Requirements | Deliverable | Check before moving on | Rough effort |
| --- | --- | --- | --- | --- | --- |
| 0 | Collection running | A1–A3, A5, A6 | Hourly jobs saving every model run and observation on an always-on machine | Seven days with a clean completeness report | 3 days |
| 1 | Target series | Target section | Rebuilt daily target from 2004; comparison with the official maximum by month | Pass criterion 1 | 4 days |
| 2 | Baselines | B1–B4 | Three baselines scored at leads 1 to 7 | Pass criterion 2 | 3 days |
| 3 | Error table | A4, C1–C3 | Backfilled forecast history; CSV and chart of every model's error by lead and season | Review with the product owner: which models stay in | 4 days |
| 4 | Corrections and test harness | D1–D5 | Walk-forward backtest engine; corrected forecasts per model and lead | Pass criterion 3; each corrected model beats its raw version | 5 days |
| 5 | Blend | E1, E2, E4 | Blended forecast mu at every lead | Pass criteria 4 and 5 | 4 days |
| 6 | Probabilities and output | F1–F4, H1–H4, J1, J2 | Forecast records and printed summaries | Pass criteria 6, 7, 9 and 11 | 5 days |
| 7 | Live day-ahead | I1–I4, J3 | Evening and settle runs on the schedule; weekly scorecard | Seven days of live records that match a re-run from raw data | 4 days |
| 8 | Same-day runs | G1–G6 | Runs at 06:00, 09:00, 12:00 and 15:00 | Pass criterion 8 | 8 days |
| 9 | Refinements | E3, F5, F6 | Each tried alone and kept only if the backtest interval excludes zero | A written keep-or-drop decision for each | 3 days each |
| 10 | Live soak | All | Final scorecard comparing live results with the backtest | Pass criterion 10 | 60 days elapsed |

The effort figures are rough estimates for one junior developer with review support, about eight working weeks before the live soak.

**Working rules**

- Do not start a milestone until the check for the one before it has passed.
- Milestone 0 keeps running through all the others. Check its completeness report every morning.
- Every "should" item is tested alone against the current best version, never bundled with another change.
- Write down every variant that was tried and its score, including the ones that lost. Picking the best of many variants on one test year flatters the winner.

## Tech stack and project layout

Use Python and keep everything small and plain. The whole system fits on a laptop; the data is megabytes, and a full refit takes seconds.

| Need | Choice | Why |
| --- | --- | --- |
| Language | Python 3.12 | Standard for this kind of work; every library below supports it |
| Data handling | pandas, numpy | Daily and hourly tables |
| Regression | scikit-learn (`Ridge`) | Requirement D1 |
| Distributions | scipy.stats | Requirements F2 and F5 |
| Online blending | opera | Requirement E3 only |
| Scoring | [scoringrules](https://github.com/frazane/scoringrules), plus own code for hit rate and calibration | Testing section |
| Charts | matplotlib | Error table chart, weekly scorecard |
| Tests | pytest | Includes the look-ahead test |
| Raw store | Compressed JSON files, one per fetch, in dated folders | Append-only and easy to inspect |
| Derived store | One SQLite database | No server to run; rebuilt from the raw store at any time |
| Configuration | One YAML file | Model list, schedule, coordinates, tuning values, upgrade dates |
| Scheduling | cron on a Linux server, or launchd on a Mac | Runs must fire while nobody is logged in |

**Where it runs.** Collection and scheduled runs need a machine that is always on and online: a small cloud server or a desktop Mac. A laptop is fine for development and backtests but not for collection, because the free sources keep full model runs for only two to three days.

**Project layout**

```
schiphol-max/
  config.yaml              models, schedule, coordinates, tuning values
  data/
    raw/                   append-only fetched responses, by date and source
    schiphol.sqlite        derived tables, rebuilt from raw
  src/
    collect/               one module per source (A1, A2, A4)
    target.py              rebuild and record the target
    access.py              the only way to read data; filters by issue time
    baselines.py           B1 to B3
    reduce.py              hourly model values to a daily maximum
    correct.py             D1 to D5
    blend.py               E1 to E4
    calibrate.py           F1 to F6
    sameday.py             G1 to G6
    deviation.py           H1 to H4
    learn.py               I1 to I4
    run.py                 entry point: one command per scheduled run
    backtest.py            walk-forward engine
    score.py               metrics and scorecard
  tests/
  reports/                 error table, scorecards, decisions log
```

**Coding rules**

- Every function that produces a forecast takes an `issue_time` argument and reads data only through `access.py`, which returns nothing dated after that time. This is how the no-look-ahead rule is enforced in code, not by care.
- The backtest and the live run call the same forecast function. There is no separate backtest version of the model.
- Every scheduled job is safe to run twice. A second run for the same issue time changes nothing.
- Tuning values (0.03, 60 days, 180 days and so on) live in the configuration file, never in the code.
- Each job writes a log line on start, on success and on failure. A failed job sends an alert.

## Risks and limits

The largest limit is the atmosphere itself: a day ahead, the uncertainty is wider than one degree, so the top degree will be wrong more often than right.

| Risk | Effect | What the design does about it |
| --- | --- | --- |
| Predictability ceiling | Day-ahead hit rate near 30%, whatever the method | Reports honest probabilities; same-day runs are where higher confidence is possible |
| Short forecast history | About 1,000 days for most models, less for the KNMI and AI models; same-day history for most models only since April 2026 | Simple regressions that need little data; a 180-day minimum before a model joins the blend |
| Target source not confirmed | The rebuilt history may not match the Weather Underground page | Pass criterion 1 tests it before anything is trained |
| The page changes | Weather Underground could change its source, format or rounding without notice | Daily comparison of the recorded target against the rebuilt value and the official maximum; alert on a run of mismatches |
| Weather-model upgrades | A model's bias shifts overnight. The European model changed in June 2023, November 2024 and May 2026 | Upgrade dates in the configuration; faster bias tracking for 30 days after each |
| Hot days | Every weather model under-forecasts the hottest days, by 0.3–0.7 °C at two days ahead in one European study. Schiphol had only 57 days at or above 30 °C in ten years | Linear correction that can go above past records; hot days scored as a separate group; larger fixes are in Later add-ons |
| Sudden weather changes | Errors nearly tripled in the research backtest on days when the maximum moved 5 °C or more | Those days are scored separately; the spread may widen with model disagreement (F6) |
| Collection gaps | Lost model runs cannot be recovered | Always-on machine, hourly completeness check, alerts |
| Terms of use | Open-Meteo's free tier is for non-commercial use; automated reading of the Weather Underground page may not be allowed | Open questions 1 and 3 |
| Flattering the winner | Trying many variants on one test year makes the best one look better than it is | Decisions log; intervals on every comparison; simpler version kept on a tie |

**If the forecasts are compared with a market.** A market price for this outcome already reflects the public forecasts. Every documented attempt found in the research to beat temperature markets with models built on public forecasts lost money, though those reports are self-published and mostly about US markets. Passing every criterion in this document does not mean the system beats a market.

## Open questions

The first three need an answer from the product owner before milestone 0; the rest are answered by the developer during the build.

- [ ] **1. Is the use commercial?** If yes, Open-Meteo needs a paid plan, or the forecasts must be pulled from the weather centres directly.
- [ ] **2. Which always-on machine runs collection?** A small cloud server or a desktop Mac.
- [ ] **3. May the Weather Underground page be read automatically?** If its terms do not allow it, the target is entered by hand each day.
- [ ] **4. Is 21:00 the right time for the evening run?** It should sit just before the moment the forecast is needed, as late as that allows.
- [ ] **5. Should market prices be logged next to each forecast?** For comparison only. This would be a new data source and is out of scope unless decided.
- [ ] **6. Who reviews each milestone check?** A junior developer should not sign off their own pass criteria.
- [ ] **7. Does ICON-D2 return values for Schiphol?** Its coverage of the Netherlands is unconfirmed. Drop it if not.
- [ ] **8. Over which hours is the MOSMIX maximum defined?** It is a 12-hour value and must be matched to the target day before it is used as a benchmark.
- [ ] **9. Does the rebuilt target match the page?** Answered by pass criterion 1.

## Later add-ons

None of these are in version 1. Each is added alone, on top of the working blend, and kept only if the walk-forward test shows a real gain.

| Add-on | What it is | Why it might help | Why it waits |
| --- | --- | --- | --- |
| Longer training history | Train corrections on the weather centres' re-runs of past years with today's model | Covers the 2018, 2019 and 2022 heat waves; one study valued 15–25 years of history at about a day of lead | Access to the re-runs has not been checked |
| Learning across stations | Fit one correction over many Dutch and nearby stations | More examples of rare events; this is how neural methods gain their edge | Needs a multi-station pipeline |
| Situation-dependent correction | Let the bias depend on wind direction, cloud and the forecast level itself | Model errors differ by weather type, and hot days are under-forecast | Splits a thin history into thinner pieces |
| Upwind errors | Use this morning's forecast errors at stations the air is coming from | A model running cold upwind is probably running cold at Schiphol | Untested idea; needs observations from other countries |
| Extra predictors | Add cloud, radiation and upper-air temperature with gradient boosting on the residual | Gains of this kind are reported once archives span several years | The archive is under three years |
| Tail-weighted training | Score errors on extreme days more heavily during fitting | Sharper hot-day forecasts | Costs some everyday accuracy |
| Observation network | A neural network on raw observations that learns only an adjustment to the blend | Most promising for the same-day runs | Large build; day-ahead gain estimated at a few percent |
| New inputs | Google's station-level AI forecast; the full spread of ensemble members | Each is a partly independent view | Access is by request, and history is short |

A fully independent AI model trained on raw observations, with no weather models as inputs, was considered and set aside. The best published systems of that kind match one corrected weather model for surface temperature; none has been shown to beat a blend of several.

## References

The design rests on the research report "Amsterdam daily max temperature models" (4 October 2026), which links every source in full. The ones a developer is most likely to need:

| Topic | Source | Supports |
| --- | --- | --- |
| Correction methods compared | [Rasp and Lerch 2018](https://arxiv.org/pdf/1805.09091) | A simple station-specific correction captures most of the gain (D1) |
| Correction on a benchmark with Dutch stations | [Höhlein et al. 2024](https://arxiv.org/pdf/2309.04452) | Size of the gain by lead; which predictors matter |
| Blending with learned weights | [Pfitzner et al., preprint](https://arxiv.org/html/2506.15217v3) | Online aggregation beat the best single corrected model by 9.5% (E1, E3) |
| Training window | [Lang et al. 2020](https://npg.copernicus.org/articles/27/23/2020/) | Train on all history, not a short sliding window (D2) |
| Running bias | [Glahn 2012](https://repository.library.noaa.gov/view/noaa/6913/noaa_6913_DS1.pdf) | Decaying-average weight of 0.025–0.05 (D3) |
| Long fit plus fast bias term | [Hamill 2021](https://repository.library.noaa.gov/view/noaa/45318/noaa_45318_DS1.pdf) | Combining D1 and D3 |
| Same-day updating | [NOAA LAMP overview](https://ams.confex.com/ams/pdfpapers/95038.pdf) | Observations add skill for about the first 12 hours (G) |
| Time-series models against weather forecasts | [Campbell and Diebold](https://www.nber.org/system/files/working_papers/w10141/w10141.pdf) | Why the baselines lose (B) |
| Model errors on hot days | [Gabler et al.](https://arxiv.org/html/2608.09972) | All models under-forecast the hottest days; written by a forecast vendor |
| Which models lead at which range | [ECMWF Technical Memo 931](https://www.ecmwf.int/sites/default/files/elibrary/092025/81680-evaluation-of-ecmwf-forecasts.pdf) | Why regional models are in the list |
| Observation-only AI forecasting | [Aardvark Weather](https://arxiv.org/html/2404.00411v3); [ECMWF Newsletter 186](https://www.ecmwf.int/en/newsletter/186/earth-system-science/ai-dop-update-medium-range-forecast-scores) | The alternative that was set aside |
| Target definition in use | [Polymarket Amsterdam market, 8 July 2026](https://polymarket.com/event/highest-temperature-in-amsterdam-on-july-8-2026) | A public contract that settles on the same Weather Underground page |

Figures marked as expectations in this document are estimates assembled from studies outside the Netherlands. The baseline figures in pass criterion 2 come from a backtest run for the research on a mirror of the KNMI files.
