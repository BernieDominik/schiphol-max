# Backtest scorecard: tuning year (1 Oct 2024 – 30 Sep 2025)

Generated 2026-10-07 17:47 UTC. Rows: forecasts with a known target.

Period: 2024-10-01 to 2025-09-30.

## By run and lead

| Group | n | Hit rate | MAE °C | Log score | 90% coverage | In five listed | Stated five |
| --- | --- | --- | --- | --- | --- | --- | --- |
| evening lead 1 | 365 | 45.8% | 0.75 | 1.426 | 92.6% | 97.5% | 97.4% |
| evening lead 2 | 365 | 36.2% | 0.90 | 1.602 | 91.8% | 95.1% | 95.5% |
| evening lead 3 | 365 | 32.9% | 1.05 | 1.746 | 92.9% | 92.3% | 90.4% |
| evening lead 4 | 365 | 25.2% | 1.27 | 1.953 | 91.5% | 87.1% | 83.9% |
| evening lead 5 | 365 | 25.2% | 1.44 | 2.116 | 92.6% | 83.3% | 73.6% |
| evening lead 6 | 365 | 18.1% | 1.77 | 2.271 | 91.8% | 78.4% | 68.1% |
| evening lead 7 | 360 | 16.1% | 2.22 | 2.526 | 88.3% | 68.1% | 63.4% |
| early lead 0 | 365 | 44.1% | 0.75 | 1.379 | 91.8% | 97.5% | 98.1% |
| morning lead 0 | 365 | 44.9% | 0.74 | 1.359 | 92.1% | 97.0% | 98.2% |
| noon lead 0 | 365 | 50.4% | 0.59 | 1.089 | 94.2% | 99.7% | 99.2% |
| afternoon lead 0 | 365 | 70.4% | 0.38 | 0.659 | 96.7% | 100.0% | 99.3% |

## Evening run, lead 1, by season

| Group | n | Hit rate | MAE °C | Log score | 90% coverage | In five listed | Stated five |
| --- | --- | --- | --- | --- | --- | --- | --- |
| DJF | 90 | 42.2% | 0.80 | 1.522 | 90.0% | 94.4% | 97.0% |
| JJA | 92 | 51.1% | 0.62 | 1.235 | 97.8% | 100.0% | 97.8% |
| MAM | 92 | 35.9% | 0.90 | 1.558 | 89.1% | 97.8% | 96.8% |
| SON | 91 | 53.8% | 0.69 | 1.390 | 93.4% | 97.8% | 98.2% |

## Difficult days (evening, lead 1)

| Group | n | Hit rate | MAE °C | Log score | 90% coverage | In five listed | Stated five |
| --- | --- | --- | --- | --- | --- | --- | --- |
| all days | 365 | 45.8% | 0.75 | 1.426 | 92.6% | 97.5% | 97.4% |
| moved ≥ 5 °C from previous day | 36 | 36.1% | 0.93 | 1.592 | 86.1% | 97.2% | 97.5% |
| at or above 30 °C | 8 | 62.5% | 0.84 | 1.534 | 87.5% | 100.0% | 97.7% |

## Calibration of every listed probability (all runs)

| Stated band | n | Average stated | Observed | Gap (pp) |
| --- | --- | --- | --- | --- |
| 0%–10% | 5055 | 4.0% | 3.8% | -0.2 |
| 10%–20% | 8767 | 14.2% | 14.3% | 0.1 |
| 20%–30% | 3094 | 24.3% | 25.7% | 1.4 |
| 30%–40% | 1836 | 34.8% | 37.6% | 2.9 |
| 40%–50% | 736 | 44.0% | 42.7% | -1.3 |
| 50%–100% | 562 | 64.4% | 67.6% | 3.2 |

## Baselines (MAE °C, hit rate)

| Run, lead | Method | n | MAE | Hit rate | Log score |
| --- | --- | --- | --- | --- | --- |
| afternoon 0 | autoregression | 365 | 1.48 | 34.8% | 1.714 |
| afternoon 0 | climatology | 365 | 2.70 | 36.7% | 1.854 |
| afternoon 0 | persistence | 365 | 1.27 | 38.6% | 1.808 |
| early 0 | autoregression | 365 | 1.93 | 16.2% | 2.244 |
| early 0 | climatology | 365 | 2.70 | 16.4% | 2.549 |
| early 0 | persistence | 365 | 2.05 | 15.6% | 2.297 |
| evening 1 | autoregression | 365 | 1.98 | 14.0% | 2.366 |
| evening 1 | climatology | 365 | 2.70 | 12.9% | 2.726 |
| evening 1 | persistence | 365 | 2.12 | 14.5% | 2.451 |
| evening 2 | autoregression | 365 | 2.55 | 14.5% | 2.666 |
| evening 2 | climatology | 365 | 2.70 | 12.9% | 2.726 |
| evening 2 | persistence | 365 | 3.00 | 14.2% | 2.904 |
| evening 3 | autoregression | 365 | 2.73 | 11.5% | 2.693 |
| evening 3 | climatology | 365 | 2.70 | 12.9% | 2.726 |
| evening 3 | persistence | 365 | 3.49 | 8.8% | 3.118 |
| evening 4 | autoregression | 365 | 2.80 | 11.0% | 2.745 |
| evening 4 | climatology | 365 | 2.70 | 12.6% | 2.726 |
| evening 4 | persistence | 365 | 3.82 | 8.5% | 3.226 |
| evening 5 | autoregression | 365 | 2.82 | 10.7% | 2.776 |
| evening 5 | climatology | 365 | 2.70 | 12.6% | 2.726 |
| evening 5 | persistence | 365 | 4.10 | 7.7% | 3.464 |
| evening 6 | autoregression | 365 | 2.81 | 11.8% | 2.782 |
| evening 6 | climatology | 365 | 2.70 | 12.6% | 2.713 |
| evening 6 | persistence | 365 | 4.18 | 6.3% | 3.517 |
| evening 7 | autoregression | 360 | 2.74 | 10.8% | 2.747 |
| evening 7 | climatology | 360 | 2.67 | 12.8% | 2.705 |
| evening 7 | persistence | 360 | 4.06 | 10.0% | 3.453 |
| morning 0 | autoregression | 365 | 1.92 | 16.7% | 2.219 |
| morning 0 | climatology | 365 | 2.70 | 17.0% | 2.516 |
| morning 0 | persistence | 365 | 2.03 | 15.9% | 2.265 |
| noon 0 | autoregression | 365 | 1.78 | 20.0% | 1.982 |
| noon 0 | climatology | 365 | 2.70 | 18.1% | 2.175 |
| noon 0 | persistence | 365 | 1.82 | 18.1% | 2.027 |

## Weather models, evening lead 1 (same days)

| Model | Kind | n | MAE | Bias |
| --- | --- | --- | --- | --- |
| ifs_hres | raw | 365 | 1.05 | -0.64 |
| ifs_hres | corrected | 365 | 0.84 | -0.01 |
| aifs_single | raw | 224 | 2.11 | -2.08 |
| aifs_single | corrected | 191 | 0.81 | 0.32 |
| icon_eu | raw | 365 | 0.81 | -0.29 |
| icon_eu | corrected | 365 | 0.78 | 0.01 |
| gfs | raw | 365 | 1.03 | 0.27 |
| gfs | corrected | 365 | 1.04 | 0.02 |
| ukmo_global | raw | 365 | 1.09 | -0.62 |
| ukmo_global | corrected | 365 | 0.97 | -0.01 |
| arpege_europe | raw | 365 | 1.18 | -0.79 |
| arpege_europe | corrected | 365 | 0.99 | 0.06 |

Standard forecast (evening lead 1): MAE 0.86 °C, hit rate 32.9%.
