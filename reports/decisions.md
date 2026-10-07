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
| Evening run time | 21:00 kept | Measured publish delays (p95, run start → archive): European 9 km model 7.3–8.0 h. At 21:00 the 12 UTC run is not yet out in summer or winter, so the evening run uses the 06 UTC run. A run at about 22:30 in winter / 22:15 in summer would catch the 12 UTC run (PRD open question 4; product owner's call). |

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
