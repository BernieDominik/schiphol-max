# Decisions log

Every variant tried and its score, including the losers (PRD working rule: picking the best of many variants on
one test year flatters the winner). Design choices are judged on the **tuning year** (1 Oct 2024 – 30 Sep 2025);
the **test year** (1 Oct 2025 – 30 Sep 2026) is reported, not tuned on.

## 2026-10-07 — build choices made before any scoring

| Topic | Choice | Why |
| --- | --- | --- |
| Time zones | All requests in UTC; Amsterdam days built with `zoneinfo` | Open-Meteo applies one offset to a whole requested range, so asking for Europe/Amsterdam shifts winter days by an hour |
| Target history | Airport reports from 2012 | IEM rows before ~2012 are rebuilt hourly values in tenths, not genuine half-hourly reports |
| Report types | IEM types 3 and 4 | IEM labels Schiphol's :25 reports "specials"; requesting routine only drops half the data |
| Availability | Publish times from Open-Meteo's open-data bucket (Jul 2026 on); otherwise run start + 95th-percentile measured delay + 10 min | Honest, conservative, and identical live and in backtest |
| Day-ahead archive | Hour by hour, the smallest "days before" whose run was out at the issue time; the assumed source run is the newest scheduled one, never older than the truth | Removes the archive's hidden look-ahead |
| Coverage | A model counts only if one run covers the whole target day (day-ahead) or the rest of it (same-day) | Never a part-day maximum |
| D1 fit | Ridge on target − raw; seasonal pair from 365 days of history | Shrinks toward slope 1 (protects hot days); a season pair is not identifiable from less than a year |
| Spread | Root-mean-square of out-of-sample blend errors (about zero), last 365 days, ≥ 60 per season, else pooled, else the anchor model | Includes leftover bias, so it errs wide rather than narrow |
| Running bias, weights | Recomputed from all outcomes in target-day order at each use | A late or out-of-order target cannot change results |
| `probabilities` | Every degree within 8 °C, 4 decimals, largest-remainder rounding to sum exactly 1 | Resolves the PRD's "sums to 1" vs "lists ≥ 0.005" |
| Standard forecast | Mean in tenths, rounded half up | Python rounds half to even |
| E3 | MLpol written in NumPy | opera is R-only and archived on CRAN; its Python port has no licence |
| Evening run time | 21:00 kept | Measured 95th-percentile publish delay of the European 9 km model: 7.3 h (00 UTC run), 6.7 h (06), 8.0 h (12), 6.8 h (18). With the 10-minute margin the 12 UTC run is usable from 20:08 UTC, i.e. 21:08 in winter and 22:08 in summer. At 21:00 the evening run therefore uses the 06 UTC run. Moving it to about 21:15 in winter and 22:15 in summer would catch the newer run (PRD open question 4; the product owner decides, as it depends on when the forecast is needed). |

## 2026-10-07 — test-year numbers seen once during development

While debugging the first trial replay (incomplete data: exact runs only up to April 2026), I printed metrics for
October 2025 – April 2026, which is part of the test year. The numbers: evening lead 1 MAE 0.66 °C, hit rate 50%,
90% coverage 95%, calibration bands off by up to 5.8 pp. No setting was changed because of them; every later
choice was judged on the tuning year only.

## 2026-10-07 — refinements (M9), each alone against the base version, tuning year

Base version: normal distribution, inverse-MAE blend, spread per season. Each variant is a full walk-forward replay
from January 2024 (`data/backtests/<variant>`). Differences are variant minus base on the same days; 95% intervals
from 1,000 resamples of whole weeks. Rule (PRD): keep only if the interval excludes zero.

| Variant | Requirement | Evening lead 1: MAE diff [95% CI] | Evening lead 1: log-score diff [95% CI] | Noon log-score diff | Worst calibration gap, evening lead 1 (bands n ≥ 100) | Decision |
| --- | --- | --- | --- | --- | --- | --- |
| Student-t, fitted tail weight (df 4–7) | F5 | 0.000 | −0.0085 [−0.024, +0.008] | +0.006 [−0.008, +0.020] | 6.8 pp in the 40–50% band, n 190 (base: 6.9 pp in the 30–40% band) | **drop** (interval includes zero) |
| Spread scaled by model disagreement | F6 | 0.000 | −0.0062 [−0.026, +0.015] | 0.000 | 6.5 pp | **drop** |
| MLpol online aggregation (opera's default, in NumPy) | E3 | −0.013 [−0.035, +0.010] | −0.012 [−0.042, +0.017] | 0.000 | 7.3 pp | **drop** |

Base version on the tuning year, evening lead 1:
- Accuracy: MAE 0.751 °C, hit rate 45.8%, log score 1.426.
- Spread: 90% coverage 92.6%.
- Calibration: the top degree is stated at 36.9% on average but comes true 45.8% of the time.
- Error shape: peaked with heavy tails (excess kurtosis 1.18); 46% of errors lie within ±0.5 °C, where a normal curve expects 38.5%.

Student-t (F5) fixes most of the shape: its bands for 0–40% come within 3 pp. But its log-score gain is not
significant, so the PRD rule drops it. If criterion 6 fails on the test year, F5 is the first remedy to put to the
product owner, because it targets exactly this shape. The spread also lags model additions: each season's spread
comes from the same season a year earlier, when fewer models were in the blend. Errors were smaller than stated in
summer and autumn 2025, and larger in January 2025.

## 2026-10-07 — after scoring the test year: spread variants, tuning year only

The first official scoring of the test year failed criteria 6 and 7 (details in `reports/checks/M6.md`). The
probabilities were too cautious: the 30–40% band came true 42.7% of the time, and 90% intervals covered 94.8%. The
tuning year had already shown the same pattern (above). So I tried one family of fixes, still judged on the tuning
year only, and changed nothing that was chosen on the test year.

| Variant | Evening lead 1: log-score diff [95% CI] | Early / noon / afternoon log-score diff | 90% coverage, evening lead 1 (seasons) | Worst calibration gap, evening lead 1 | Same-day worst gap | Decision |
| --- | --- | --- | --- | --- | --- | --- |
| Base (as specified: spread per season, 365 days) | — | — | 92.6% (DJF 90.0, MAM 89.1, JJA 97.8, SON 93.4) | 6.9 pp | 3.6 pp | **kept** |
| F5 Student-t, tail weight per run | −0.0085 [−0.024, +0.008] | −0.007 / −0.001 / 0.000 | 91.2% (JJA 96.7) | 6.8 pp | 2.4 pp | drop |
| F1 variant: spread level from the last 120 days, seasonal shape from two years | −0.0060 [−0.015, +0.002] | +0.004 / +0.001 / 0.000 | 92.9% (JJA 97.8) | 5.1 pp | 4.0 pp | drop |
| F1 variant + F5 | −0.0149 [−0.031, +0.002] | −0.006 / −0.001 / −0.002 | 91.2% (JJA 95.7) | 8.9 pp | 2.8 pp | drop |

No variant's interval excludes zero, so the simpler base version stays (PRD rule). One year cannot separate these.
With 100–450 listed probabilities per band, the binomial noise in a band is about 2–3 pp, so the 5 pp bar sits at
about two standard errors.

What to do next is the product owner's call. My recommendation is to let the live soak decide. By then
HARMONIE and ICON-D2 are in the blend (they reach 180 days of honest history in October 2026), and live errors give
the spread a fresh, independent sample. If the soak shows the same caution, adopt F1 variant + F5, which had the
best tuning-year log score.

## 2026-10-07 — hands-off operation (product owner: "do all next steps")

| Topic | Decision | Why |
| --- | --- | --- |
| Target from 8 Oct 2026 | The highest half-hourly airport report of the Amsterdam day, settled automatically. Hand-entered WU values are optional checks. | Nobody will type the WU value daily. WU's terms forbid automated reading. The Polymarket resolutions that settle on the same page are not reachable from the Netherlands, and I will not route around a geo-block. The rebuilt series is already the stand-in for all training history. |
| Criterion 1 | Stays open | It needs a person to read 60 WU pages (`reports/wu_check_sheet.csv`, about 30 minutes). Until then the system forecasts the airport-report maximum, which the WU page is believed to be built from (unconfirmed). |
| Live availability | From go-live (7 Oct 2026, 18:30 UTC), a value counts as available no earlier than 30 minutes before we first stored it | A value that reached us late (failed fetch, archive lag) must not appear in a re-run of a forecast made without it. The 30 minutes cover the hourly job starting after the slot. The target is frozen at the moment it is settled. |
| Method settings | Blend method, distribution and spread option are stored in every parameter set | A later change applies from the next refit, and re-runs always use the settings that were in force |
| Milestones | Advance automatically: 7 good days, then same-day runs; 60 good days, then criterion 10 and the final report | No sign-offs |
| Calibration (pre-registered, before any live data) | At the end of the soak, replay the soak period with each refinement (F5, F1 variant, both, E3, F6). Adopt the one with the best log score on the day-ahead forecast only if its 95% interval (whole-week bootstrap) excludes zero; otherwise change nothing. | The PRD's own rule, applied to fresh data that no design choice has seen |
| Healthchecks.io | Not set up | It needs an account in your name; GitHub already emails you when a run fails |
| Evening run time, model list | Unchanged: 21:00, all eight models | My recommendations, taken as decided |
| Repository visibility (7 Oct, 23:00 UTC) | Public | GitHub ran no timed schedules for this repository while it was private on a free account (none in 5 hours, even after re-registering); runs started by hand always worked. Making it public was the product owner's choice: free, and GitHub runs schedules there. The history was scanned first: no keys, passwords or work email. |
| Hourly trigger (10 Oct) | cron-job.org calls GitHub's "run workflow" API every hour at :02 with a fine-grained token (Actions read/write, this repository only); GitHub's own :17/:47 schedule stays as a backup | Deep dive, 8 Oct: GitHub's scheduler created 0 of 8 runs of a bare 5-minute probe and 1 of about 40 hourly slots, while manual runs started in seconds. This matches a GitHub-side fault reported since 26 Aug 2026 (community discussions 206019, 208916) and not acknowledged by GitHub. A first test from cron-job.org returned 204 and the run succeeded. Upkeep: renew the token before it expires (cron-job.org emails on failure). GitHub marks API version 2022-11-28 deprecated, with sunset 10 Mar 2028, so update the header before then. |
