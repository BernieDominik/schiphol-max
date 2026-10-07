"""I1–I4 support: paired history (raw forecast, target) and the running bias.

Learning is recomputed from the record of outcomes in target-day order every time it is needed, rather
than mutated in place, so a target typed in late (or out of order) cannot change any result.
"""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np

from .access import Data
from .config import Config
from .correct import predict
from .reduce import RawForecast, raw_forecast
from .schedule import issue_time, keys
from .timeutil import daterange


class Pairs:
    """Raw forecasts for every model, (run, lead) and target day, with the target and when it became known.

    Every raw forecast is computed with the data available at its own issue time, so arrays may safely
    run ahead of the replay clock: callers mask by issue time and target availability."""

    def __init__(self, cfg: Config, data: Data, first_day: date, last_day: date):
        self.cfg, self.data = cfg, data
        self.first_day, self.last_day = first_day, last_day
        self.raw: dict[tuple[str, str, int, date], RawForecast | None] = {}
        self.arrays: dict[tuple[str, tuple[str, int]], dict[str, np.ndarray]] = {}
        days = list(daterange(first_day, last_day))
        self.days = days
        self.day_ord = np.array([d.toordinal() for d in days], dtype=np.int64)
        self.doy = np.array([d.timetuple().tm_yday for d in days], dtype=float)
        y = np.full(len(days), np.nan)
        y_avail = np.full(len(days), np.iinfo(np.int64).max, dtype=np.int64)
        for i, d in enumerate(days):
            t = data.target(d)
            if t is not None:
                y[i], y_avail[i] = t[0], t[2]
        self.y, self.y_avail = y, y_avail
        self.issue: dict[tuple[str, int], np.ndarray] = {
            k: np.array([issue_time(cfg, k[0], k[1], d) for d in days], dtype=np.int64) for k in keys(cfg)}

    def get_raw(self, model: str, key: tuple[str, int], day: date) -> RawForecast | None:
        ck = (model, key[0], key[1], day)
        if ck not in self.raw:
            self.raw[ck] = raw_forecast(self.data, model, key[1], day, issue_time(self.cfg, key[0], key[1], day))
        return self.raw[ck]

    def series(self, model: str, key: tuple[str, int]) -> dict[str, np.ndarray]:
        """x (raw forecast, NaN when missing) for every day of the range."""
        ak = (model, key)
        if ak not in self.arrays:
            x = np.full(len(self.days), np.nan)
            for i, d in enumerate(self.days):
                r = self.get_raw(model, key, d)
                if r is not None:
                    x[i] = r.value
            self.arrays[ak] = {"x": x}
        return self.arrays[ak]

    def known(self, model: str, key: tuple[str, int], as_of: int) -> np.ndarray:
        """Index of days with a raw forecast issued before `as_of` and a target known by `as_of`."""
        x = self.series(model, key)["x"]
        return np.nonzero(~np.isnan(x) & (self.issue[key] < as_of) & (self.y_avail <= as_of))[0]

    def bias_weight(self, model: str) -> np.ndarray:
        """D3/I3 weight for each day of the range (faster tracking for 30 days after a model upgrade)."""
        key = ("_w", model)
        if key not in self.arrays:
            self.arrays[key] = {"w": bias_weights(self.cfg, model, self.days)}
        return self.arrays[key]["w"]

    def index_of(self, day: date) -> int:
        return day.toordinal() - self.first_day.toordinal()

    def extend(self, last_day: date) -> None:
        """Grow the day range (used when a long-lived process runs past its initial horizon)."""
        if last_day <= self.last_day:
            return
        fresh = Pairs(self.cfg, self.data, self.first_day, last_day)
        fresh.raw = self.raw
        self.__dict__.update(fresh.__dict__)


def bias_weights(cfg: Config, model: str, days: list[date]) -> np.ndarray:
    corr = cfg["correction"]
    w = np.full(len(days), corr["running_bias_weight"], dtype=float)
    ords = np.array([d.toordinal() for d in days])
    for up in cfg.get("upgrades") or []:
        if up["model"] != model:
            continue
        start = date.fromisoformat(up["date"]).toordinal()
        w[(ords >= start) & (ords < start + corr["upgrade_days"])] = corr["upgrade_bias_weight"]
    return w


def running_bias(residuals: np.ndarray, weights: np.ndarray) -> float:
    """D3 replayed over date-ordered residuals: r ← (1 − w) r + w e, starting from r = 0.
    Closed form: r = Σ e_i w_i Π_{j>i} (1 − w_j)."""
    if len(residuals) == 0:
        return 0.0
    keep = np.log1p(-weights)
    after = np.concatenate([np.cumsum(keep[::-1])[::-1][1:], [0.0]])
    return float(np.sum(residuals * weights * np.exp(after)))


def corrected_history(pairs: Pairs, model: str, key: tuple[str, int], params: dict, as_of: int):
    """(index, residuals of the regression) for days known at `as_of`, in date order."""
    idx = pairs.known(model, key, as_of)
    x = pairs.series(model, key)["x"][idx]
    yhat = predict(params, x, pairs.doy[idx])
    return idx, pairs.y[idx] - yhat


__all__ = ["Pairs", "running_bias", "bias_weights", "corrected_history", "keys"]
