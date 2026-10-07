"""E1–E4: blend the corrected models into one number, mu.

E1: weights proportional to 1 / MAE over the last 60 days at that (run, lead), renormalised over the
models present (E2). E3 (variant): online expert aggregation by MLpol, the default rule of the
opera package (Gaillard, Stoltz & van Erven 2014), written here in NumPy because opera is R-only.
"""

from __future__ import annotations

import numpy as np


def inverse_mae_weights(maes: dict[str, float]) -> dict[str, float]:
    inv = {m: 1.0 / max(v, 0.05) for m, v in maes.items()}
    total = sum(inv.values())
    return {m: v / total for m, v in inv.items()}


def blend(corrected: dict[str, float], weights: dict[str, float]) -> float:
    total = sum(weights[m] for m in corrected if m in weights)
    return float(sum(corrected[m] * weights[m] for m in corrected if m in weights) / total)


def mlpol_weights(history: list[tuple[dict[str, float], float]], experts: list[str]) -> dict[str, float]:
    """MLpol with squared loss over a date-ordered history of (expert forecasts, outcome).

    Experts missing on a day abstain: the mixture is renormalised over those present and only their
    regrets are updated. Returns the weights for the next forecast, over `experts`."""
    R = {k: 0.0 for k in experts}       # cumulative linearised regret
    S = {k: 0.0 for k in experts}       # cumulative squared regret (sets each learning rate)

    def current() -> dict[str, float]:
        eta = {k: 1.0 / (1.0 + S[k]) for k in experts}
        raw = {k: eta[k] * max(R[k], 0.0) for k in experts}
        tot = sum(raw.values())
        if tot <= 0:
            return {k: 1.0 / len(experts) for k in experts}
        return {k: v / tot for k, v in raw.items()}

    for forecasts, y in history:
        present = [k for k in experts if k in forecasts]
        if not present:
            continue
        w = current()
        wp = {k: w[k] for k in present}
        tot = sum(wp.values()) or 1.0
        p = sum(forecasts[k] * wp[k] for k in present) / tot
        grad = 2.0 * (p - y)
        for k in present:
            r = grad * (p - forecasts[k])
            R[k] += r
            S[k] += r * r
    return current()
