"""H1–H4: how the calibrated forecast relates to the standard forecast (plain average of the raw forecasts)."""

from __future__ import annotations

import math


def standard_forecast(raws: list[float]) -> int:
    """Average in tenths of a degree, rounded half up (Python's round() would round half to even)."""
    tenths = [round(r * 10) for r in raws]
    mean = sum(tenths) / len(tenths) / 10
    return int(math.floor(mean + 0.5))


def against_standard(probs: dict[int, float], std: int, miss_c: int) -> dict:
    above = sum(v for k, v in probs.items() if k > std)
    on = probs.get(std, 0.0)
    below = sum(v for k, v in probs.items() if k < std)
    miss = sum(v for k, v in probs.items() if abs(k - std) >= miss_c)
    return {"p_above_standard": round(above, 4), "p_on_standard": round(on, 4),
            "p_below_standard": round(below, 4), "p_miss_2_or_more": round(miss, 4)}
