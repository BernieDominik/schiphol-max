# Pass criteria for version 1

Generated 2026-10-07 18:12 UTC from the official record chain (`data/records`).

Test year: 2025-10-01 to 2026-09-30 (walk-forward backtest; nothing fitted on a day it forecasts).

| # | Criterion | Status | Measured |
| --- | --- | --- | --- |
| 1 | Rebuilt target matches the WU page | PENDING | open: needs a person to read 60 WU pages (WU forbids automated reading); the system uses the airport-report maximum meanwhile |
| 2 | Baselines reproduce the research figures | PASS | persistence 2.00, climatology 2.68, autoregression 1.89 |
| 3 | No look-ahead | PASS | 8 cut-offs |
| 4 | Day-ahead blend beats its inputs | FAIL | blend MAE 0.70, log score 1.338 |
| 5 | Day-ahead blend beats the baselines | PASS | blend MAE 0.70 vs autoregression 2.04 (66% lower) |
| 6 | Probabilities are honest | FAIL | a band is off by more than 5 pp |
| 7 | Spread is honest | FAIL | 94.8%; 95.7% |
| 8 | Same-day runs are measured | PASS | measured for all four issue hours |
| 9 | Past forecasts can be reproduced | PASS | 4964 files re-run, 0 differences |
| 10 | It runs unattended (60 days) | PENDING | 60-day live soak not started |
| 11 | The five-degree table is honest | PASS | 98.4% vs 97.7%; 98.9% vs 98.2% |

Milestone reports: [M1](M1.md) · [M2](M2.md) · [M4](M4.md) · [M5](M5.md) · [M6](M6.md) · [M8](M8.md). M0, M3, M7, M9 and M10 are written separately ([M0](M0.md), [M3](M3.md), [M7](M7.md), [M9](M9.md), [M10](M10.md)).
