"""G1–G6: same-day updates from the airport reports seen so far today.

G1 max so far comes from `Data.max_so_far`. G2: each model's error so far is the observed temperature
minus its corrected hourly temperature (raw hourly + that model's current correction of the daily
maximum), averaged over the reports of the last three hours. G3: mu moves by a fitted intercept plus a
fitted fraction of the blended error, one pair per issue hour. G4/G5/G6 live in the spread table and
`calibrate.degree_probabilities`.
"""

from __future__ import annotations

import numpy as np

from .access import Data
from .timeutil import HOUR


def model_error_so_far(data: Data, run, offset: float, issue: int, window_h: int) -> float | None:
    obs_t, obs_v = data.reports_between(issue - window_h * HOUR, issue, issue)
    if run is None or len(obs_t) == 0:
        return None
    valid, temp = run.values(issue - (window_h + 1) * HOUR, issue + HOUR)
    if len(valid) < 2:
        return None
    inside = (obs_t >= valid[0]) & (obs_t <= valid[-1])
    if not inside.any():
        return None
    model_at_obs = np.interp(obs_t[inside], valid, temp) + offset
    return float(np.mean(obs_v[inside] - model_at_obs))


def blended_error(errors: dict[str, float | None], weights: dict[str, float]) -> float | None:
    have = {m: e for m, e in errors.items() if e is not None and weights.get(m, 0) > 0}
    if not have:
        return None
    tot = sum(weights[m] for m in have)
    return float(sum(e * weights[m] for m, e in have.items()) / tot)


def fit_shift(residual: np.ndarray, err: np.ndarray, min_records: int) -> dict:
    """G3: residual (target − mu before shift) ≈ a + k · error so far."""
    if len(err) < min_records:
        return {"a": 0.0, "k": 0.0, "n": int(len(err))}
    X = np.column_stack([np.ones(len(err)), err])
    (a, k), *_ = np.linalg.lstsq(X, residual, rcond=None)
    return {"a": float(a), "k": float(k), "n": int(len(err))}
