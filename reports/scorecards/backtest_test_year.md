# Backtest scorecard: test year (1 Oct 2025 – 30 Sep 2026)

Generated 2026-10-07 17:47 UTC. Rows: forecasts with a known target.

Period: 2025-10-01 to 2026-09-30.

## By run and lead

| Group | n | Hit rate | MAE °C | Log score | 90% coverage | In five listed | Stated five |
| --- | --- | --- | --- | --- | --- | --- | --- |
| evening lead 1 | 365 | 45.2% | 0.70 | 1.338 | 94.8% | 98.4% | 97.7% |
| evening lead 2 | 365 | 40.8% | 0.79 | 1.489 | 94.8% | 97.5% | 95.6% |
| evening lead 3 | 365 | 37.3% | 0.90 | 1.626 | 93.7% | 95.3% | 93.3% |
| evening lead 4 | 365 | 28.8% | 1.13 | 1.858 | 91.0% | 90.4% | 88.6% |
| evening lead 5 | 365 | 28.2% | 1.37 | 2.004 | 89.9% | 84.4% | 85.4% |
| evening lead 6 | 365 | 20.0% | 1.68 | 2.218 | 89.6% | 78.1% | 77.6% |
| evening lead 7 | 365 | 18.1% | 2.17 | 2.502 | 87.7% | 66.3% | 63.4% |
| early lead 0 | 365 | 46.0% | 0.71 | 1.345 | 95.1% | 98.4% | 97.1% |
| morning lead 0 | 365 | 43.3% | 0.71 | 1.324 | 95.9% | 98.6% | 97.5% |
| noon lead 0 | 365 | 49.9% | 0.62 | 1.160 | 95.6% | 99.2% | 99.0% |
| afternoon lead 0 | 365 | 75.1% | 0.40 | 0.735 | 96.2% | 99.5% | 99.3% |

## Evening run, lead 1, by season

| Group | n | Hit rate | MAE °C | Log score | 90% coverage | In five listed | Stated five |
| --- | --- | --- | --- | --- | --- | --- | --- |
| DJF | 90 | 44.4% | 0.74 | 1.372 | 93.3% | 98.9% | 97.6% |
| JJA | 92 | 37.0% | 0.83 | 1.499 | 92.4% | 95.7% | 97.6% |
| MAM | 92 | 55.4% | 0.60 | 1.302 | 96.7% | 98.9% | 97.0% |
| SON | 91 | 44.0% | 0.61 | 1.177 | 96.7% | 100.0% | 98.4% |

## Difficult days (evening, lead 1)

| Group | n | Hit rate | MAE °C | Log score | 90% coverage | In five listed | Stated five |
| --- | --- | --- | --- | --- | --- | --- | --- |
| all days | 365 | 45.2% | 0.70 | 1.338 | 94.8% | 98.4% | 97.7% |
| moved ≥ 5 °C from previous day | 43 | 32.6% | 1.10 | 1.935 | 76.7% | 90.7% | 97.7% |
| at or above 30 °C | 10 | 30.0% | 0.64 | 1.183 | 100.0% | 100.0% | 97.7% |

## Calibration of every listed probability (all runs)

| Stated band | n | Average stated | Observed | Gap (pp) |
| --- | --- | --- | --- | --- |
| 0%–10% | 5257 | 4.4% | 3.2% | -1.2 |
| 10%–20% | 7533 | 14.5% | 12.9% | -1.6 |
| 20%–30% | 4052 | 24.5% | 26.9% | 2.4 |
| 30%–40% | 1995 | 34.3% | 38.7% | 4.4 |
| 40%–50% | 834 | 43.7% | 44.4% | 0.7 |
| 50%–100% | 404 | 66.5% | 74.5% | 8.0 |

## Baselines (MAE °C, hit rate)

| Run, lead | Method | n | MAE | Hit rate | Log score |
| --- | --- | --- | --- | --- | --- |
| afternoon 0 | autoregression | 365 | 1.52 | 36.2% | 1.732 |
| afternoon 0 | climatology | 365 | 2.72 | 37.3% | 1.856 |
| afternoon 0 | persistence | 365 | 1.31 | 39.5% | 1.841 |
| early 0 | autoregression | 365 | 2.00 | 18.9% | 2.295 |
| early 0 | climatology | 365 | 2.72 | 16.7% | 2.583 |
| early 0 | persistence | 365 | 2.14 | 14.2% | 2.341 |
| evening 1 | autoregression | 365 | 2.04 | 17.3% | 2.406 |
| evening 1 | climatology | 365 | 2.72 | 15.3% | 2.763 |
| evening 1 | persistence | 365 | 2.20 | 14.0% | 2.498 |
| evening 2 | autoregression | 365 | 2.51 | 12.1% | 2.633 |
| evening 2 | climatology | 365 | 2.72 | 15.6% | 2.763 |
| evening 2 | persistence | 365 | 2.87 | 13.2% | 2.831 |
| evening 3 | autoregression | 365 | 2.60 | 13.4% | 2.663 |
| evening 3 | climatology | 365 | 2.72 | 15.6% | 2.764 |
| evening 3 | persistence | 365 | 3.15 | 10.7% | 2.942 |
| evening 4 | autoregression | 365 | 2.62 | 14.0% | 2.685 |
| evening 4 | climatology | 365 | 2.72 | 15.9% | 2.764 |
| evening 4 | persistence | 365 | 3.27 | 9.3% | 3.040 |
| evening 5 | autoregression | 365 | 2.70 | 14.2% | 2.723 |
| evening 5 | climatology | 365 | 2.72 | 16.2% | 2.764 |
| evening 5 | persistence | 365 | 3.49 | 7.7% | 3.054 |
| evening 6 | autoregression | 365 | 2.76 | 11.8% | 2.746 |
| evening 6 | climatology | 365 | 2.72 | 16.2% | 2.764 |
| evening 6 | persistence | 365 | 3.72 | 8.8% | 3.184 |
| evening 7 | autoregression | 365 | 2.75 | 14.8% | 2.779 |
| evening 7 | climatology | 365 | 2.72 | 16.4% | 2.763 |
| evening 7 | persistence | 365 | 3.92 | 5.8% | 3.265 |
| morning 0 | autoregression | 365 | 1.98 | 18.9% | 2.264 |
| morning 0 | climatology | 365 | 2.72 | 16.7% | 2.547 |
| morning 0 | persistence | 365 | 2.11 | 14.2% | 2.302 |
| noon 0 | autoregression | 365 | 1.84 | 21.4% | 2.011 |
| noon 0 | climatology | 365 | 2.72 | 20.8% | 2.220 |
| noon 0 | persistence | 365 | 1.88 | 17.8% | 2.054 |

## Weather models, evening lead 1 (same days)

| Model | Kind | n | MAE | Bias |
| --- | --- | --- | --- | --- |
| ifs_hres | raw | 365 | 0.92 | -0.57 |
| ifs_hres | corrected | 365 | 0.79 | 0.03 |
| aifs_single | raw | 365 | 1.39 | -1.28 |
| aifs_single | corrected | 365 | 0.77 | 0.02 |
| harmonie_nl | raw | 181 | 2.27 | 2.05 |
| harmonie_nl | corrected | 150 | 1.12 | -0.48 |
| icon_d2 | raw | 181 | 0.75 | -0.11 |
| icon_d2 | corrected | 150 | 0.79 | -0.17 |
| icon_eu | raw | 365 | 0.76 | -0.16 |
| icon_eu | corrected | 365 | 0.72 | 0.01 |
| gfs | raw | 365 | 1.03 | 0.22 |
| gfs | corrected | 365 | 1.00 | 0.00 |
| ukmo_global | raw | 365 | 0.96 | -0.33 |
| ukmo_global | corrected | 365 | 0.92 | 0.02 |
| arpege_europe | raw | 365 | 1.22 | -0.63 |
| arpege_europe | corrected | 365 | 1.00 | -0.00 |

Standard forecast (evening lead 1): MAE 0.71 °C, hit rate 43.6%.
