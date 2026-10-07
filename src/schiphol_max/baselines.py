"""B1–B4: three deliberately simple yardsticks, scored alongside every real forecast.

B1 persistence: the forecast equals the latest complete-or-nearly-complete day's maximum.
B2 climatology: a + b·t + two harmonic pairs of the day of year (t in years).
B3 autoregression: climatology plus a fitted fraction of the latest day's departure from climatology.
"""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np

from .access import Data
from .timeutil import from_ts, local_date, AMS

METHODS = ("persistence", "climatology", "autoregression")


def _t_years(days) -> np.ndarray:
    return np.array([d.year + (d.timetuple().tm_yday - 1) / 365.25 - 2000 for d in days])


def clim_design(days) -> np.ndarray:
    t = _t_years(days)
    doy = np.array([d.timetuple().tm_yday for d in days], dtype=float)
    cols = [np.ones(len(days)), t]
    for k in (1, 2):
        a = 2 * np.pi * k * doy / 365.25
        cols += [np.sin(a), np.cos(a)]
    return np.column_stack(cols)


def fit_climatology(days, values) -> list[float]:
    coef, *_ = np.linalg.lstsq(clim_design(days), np.asarray(values, dtype=float), rcond=None)
    return [float(c) for c in coef]


def climatology(coef, days) -> np.ndarray:
    return clim_design(days) @ np.asarray(coef)


def fit_ar(days: list[date], values: np.ndarray, coef, lag: int) -> float:
    lookup = dict(zip(days, values - climatology(coef, days)))
    prev, cur = [], []
    for d, a in lookup.items():
        p = lookup.get(d - timedelta(days=lag))
        if p is not None:
            prev.append(p)
            cur.append(a)
    prev, cur = np.array(prev), np.array(cur)
    return float(np.dot(prev, cur) / np.dot(prev, prev)) if len(prev) else 0.0


def fit_baselines(days: list[date], values: np.ndarray, max_lag: int = 8) -> dict:
    """Fit on a target history; spreads are the root-mean-square in-sample error per method and lag."""
    coef = fit_climatology(days, values)
    clim = climatology(coef, days)
    lookup = dict(zip(days, values))
    out = {"climatology": coef, "ar": {}, "sigma": {m: {} for m in METHODS}}
    out["sigma"]["climatology"] = {str(l): float(np.sqrt(np.mean((values - clim) ** 2))) for l in range(0, max_lag + 1)}
    for lag in range(1, max_lag + 1):
        phi = fit_ar(days, values, coef, lag)
        out["ar"][str(lag)] = phi
        pe, ae = [], []
        cl = dict(zip(days, clim))
        for d, y in lookup.items():
            p = lookup.get(d - timedelta(days=lag))
            if p is None:
                continue
            pe.append(y - p)
            ae.append(y - (cl[d] + phi * (p - cl[d - timedelta(days=lag)])))
        out["sigma"]["persistence"][str(lag)] = float(np.sqrt(np.mean(np.square(pe))))
        out["sigma"]["autoregression"][str(lag)] = float(np.sqrt(np.mean(np.square(ae))))
    return out


def reference_value(data: Data, issue: int) -> tuple[date, int] | None:
    """Latest day whose maximum is (nearly) known at `issue`: today after 18:00 local, else yesterday."""
    local = from_ts(issue).astimezone(AMS)
    today = local.date()
    if local.hour >= 18:
        v = data.max_so_far(today, issue)
        return (today, v) if v is not None else None
    y = today - timedelta(days=1)
    v = data.max_so_far(y, issue)
    return (y, v) if v is not None else None


def baseline_forecasts(params: dict, data: Data, target_day: date, issue: int) -> dict[str, tuple[float, float]] | None:
    """{method: (mu, sigma)} for the target day, using only data available at `issue`."""
    ref = reference_value(data, issue)
    if ref is None or not params:
        return None
    ref_day, ref_val = ref
    lag = max(1, (target_day - ref_day).days)
    lag_key = str(min(lag, 8))
    coef = params["climatology"]
    clim_t, clim_r = climatology(coef, [target_day, ref_day])
    phi = params["ar"].get(lag_key, 0.0)
    return {
        "persistence": (float(ref_val), params["sigma"]["persistence"][lag_key]),
        "climatology": (float(clim_t), params["sigma"]["climatology"][lag_key]),
        "autoregression": (float(clim_t + phi * (ref_val - clim_r)), params["sigma"]["autoregression"][lag_key]),
    }


def criterion2(data: Data) -> dict:
    """Pass criterion 2: on the KNMI official maximum, fit 1971–2015, test 2016–2025, lead 1."""
    days = sorted(d for d in data.knmi if date(1971, 1, 1) <= d <= date(2025, 12, 31))
    tx = {d: data.knmi[d][0] for d in days}
    train = [d for d in days if d.year <= 2015]
    test = [d for d in days if d.year >= 2016 and (d - timedelta(days=1)) in tx]
    coef = fit_climatology(train, [tx[d] for d in train])
    phi = fit_ar(train, np.array([tx[d] for d in train]), coef, 1)
    y = np.array([tx[d] for d in test])
    prev = np.array([tx[d - timedelta(days=1)] for d in test])
    clim = climatology(coef, test)
    clim_prev = climatology(coef, [d - timedelta(days=1) for d in test])
    return {
        "n_test_days": len(test),
        "ar_coefficient": round(phi, 3),
        "persistence": round(float(np.mean(np.abs(y - prev))), 3),
        "climatology": round(float(np.mean(np.abs(y - clim))), 3),
        "autoregression": round(float(np.mean(np.abs(y - (clim + phi * (prev - clim_prev))))), 3),
    }


__all__ = ["METHODS", "fit_baselines", "baseline_forecasts", "criterion2", "local_date"]
