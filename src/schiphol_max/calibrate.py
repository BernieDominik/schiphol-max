"""F1–F8: a spread around mu, turned into a probability for each whole degree.

P(k) = F(k + 0.5) − F(k − 0.5) for every degree within 8 °C of mu, each floored at 0.001 (F4).
On same-day runs every degree below the maximum so far shares 0.002 in total (G5).
Probabilities are rounded to 4 decimals with largest-remainder rounding so the list sums to exactly 1.
"""

from __future__ import annotations

import math

import numpy as np
from scipy import stats


def cdf(x: np.ndarray, mu: float, sigma: float, dist: str = "normal", df: float | None = None) -> np.ndarray:
    if dist == "student_t" and df:
        scale = sigma * math.sqrt((df - 2) / df) if df > 2 else sigma
        return stats.t.cdf((x - mu) / scale, df)
    return stats.norm.cdf((x - mu) / sigma)


def round_to_one(p: dict[int, float], decimals: int) -> dict[int, float]:
    """Largest-remainder rounding: every value to `decimals`, total exactly 1."""
    unit = 10 ** decimals
    keys = sorted(p)
    total = sum(p.values())
    exact = [p[k] / total * unit for k in keys]
    floors = [math.floor(v) for v in exact]
    short = unit - sum(floors)
    order = sorted(range(len(keys)), key=lambda i: (-(exact[i] - floors[i]), keys[i]))
    for i in order[:short]:
        floors[i] += 1
    return {k: floors[i] / unit for i, k in enumerate(keys)}


def degree_probabilities(mu: float, sigma: float, cal: dict, *, dist: str = "normal", df: float | None = None,
                         max_so_far: int | None = None) -> dict[int, float]:
    rng = cal["floor_range_c"]
    lo, hi = math.ceil(mu - rng), math.floor(mu + rng)
    if max_so_far is not None:
        hi = max(hi, max_so_far + 3)
        lo = min(lo, max_so_far - 1)
    ks = np.arange(lo, hi + 1)
    p = cdf(ks + 0.5, mu, sigma, dist, df) - cdf(ks - 0.5, mu, sigma, dist, df)
    p = np.maximum(p, cal["floor_probability"])                      # F4
    below = ks < max_so_far if max_so_far is not None else np.zeros(len(ks), bool)
    if below.any():                                                  # G5
        share = p[below] / p[below].sum()
        p[below] = cal["below_max_total"] * share
        p[~below] = p[~below] / p[~below].sum() * (1 - cal["below_max_total"])
    else:
        p = p / p.sum()
    return round_to_one({int(k): float(v) for k, v in zip(ks, p)}, cal["decimals"])


def top_degree(probs: dict[int, float], mu: float) -> int:
    best = max(probs.values())
    tied = [k for k, v in probs.items() if v == best]
    return min(tied, key=lambda k: (abs(k - mu), k))


def five_degree_table(probs: dict[int, float], top: int, decimals: int) -> tuple[list[dict], float]:
    table = [{"degree": k, "probability": probs.get(k, 0.0)} for k in range(top - 2, top + 3)]
    outside = round(1.0 - sum(t["probability"] for t in table), decimals)        # F7: not rescaled
    return table, max(outside, 0.0)


def mid_pit(probs: dict[int, float], target: int) -> float:
    """Where the target falls in the stated distribution (0–1); used for interval coverage."""
    below = sum(v for k, v in probs.items() if k < target)
    return below + 0.5 * probs.get(target, 0.0)


def fit_t_df(z: np.ndarray, candidates=(3, 4, 5, 7, 10, 15, 20, 30, 50)) -> float:
    """F5: tail weight chosen by likelihood of standardised past errors (unit-variance Student-t)."""
    best, best_ll = None, -np.inf
    for df in candidates:
        scale = math.sqrt((df - 2) / df)
        ll = float(np.sum(stats.t.logpdf(z / scale, df) - math.log(scale)))
        if ll > best_ll:
            best, best_ll = df, ll
    return float(best)
