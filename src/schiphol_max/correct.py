"""D1–D5: one small linear correction per weather model and (run, lead).

The fit is done on the target minus the raw forecast, so ridge regularisation pulls toward
"trust the model" (slope 1) rather than toward the average, which would undercut record-warm days.
The seasonal pair is added only once a year of history exists. No tree-based learners (D5).
"""

from __future__ import annotations

import numpy as np
from sklearn.linear_model import Ridge

TWO_PI = 2 * np.pi


def seasonal(doy: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    a = TWO_PI * np.asarray(doy, dtype=float) / 365.25
    return np.sin(a), np.cos(a)


def fit_correction(x: np.ndarray, y: np.ndarray, doy: np.ndarray, alpha: float, seasonal_after: int) -> dict:
    use_season = len(x) >= seasonal_after
    feats = [x]
    if use_season:
        s, c = seasonal(doy)
        feats += [s, c]
    X = np.column_stack(feats)
    model = Ridge(alpha=alpha).fit(X, y - x)
    coef = [float(v) for v in model.coef_]
    return {"a": float(model.intercept_), "b": 1.0 + coef[0],
            "c": coef[1] if use_season else 0.0, "e": coef[2] if use_season else 0.0,
            "n": int(len(x)), "seasonal": use_season}


def predict(p: dict, x: np.ndarray | float, doy: np.ndarray | float) -> np.ndarray | float:
    s, c = seasonal(doy)
    return p["a"] + p["b"] * np.asarray(x, dtype=float) + p["c"] * s + p["e"] * c
