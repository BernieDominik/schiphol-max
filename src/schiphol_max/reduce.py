"""Step 2 of the pipeline: a weather model's hourly values reduced to its maximum for the target day."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np

from .access import Data
from .timeutil import HOUR, day_bounds


@dataclass
class RawForecast:
    model: str
    value: float                    # the raw forecast in °C
    run: int | None                 # run start (UTC) or None when stitched from the day-ahead archive
    source: str                     # "single" (exact run) or "previous" (day-ahead archive, hour by hour)
    stale: bool
    model_max: float                # the model's own maximum over the hours it covered
    run_obj: object | None = None   # the exact run, for same-day error tracking


def raw_forecast(data: Data, model: str, lead: int, target_day: date, issue: int) -> RawForecast | None:
    """Raw forecast available at `issue`.

    Day-ahead (lead >= 1): the newest published run covering every hour of the target day; before the
    exact-run archive starts, the day-ahead archive stitched hour by hour from runs that were out.
    Same-day (lead 0): the newest exact run covering the rest of the day; the raw value is the higher
    of the observed maximum so far and the model's maximum over the remaining hours.
    A maximum over part of the day is never used: a model without coverage is missing (E2).
    """
    start, end = day_bounds(target_day)
    if lead >= 1:
        run = data.newest_run(model, issue, start, end)
        if run is not None:
            _, temps = run.values(start, end)
            mx = float(temps.max())
            return RawForecast(model, mx, run.run, "single", data.is_stale(model, run.run, issue), mx, run)
        hours = list(range(start, end, HOUR))
        vals = data.previous_runs_hours(model, hours, issue)
        if vals is None:
            return None
        mx = float(np.max(vals))
        return RawForecast(model, mx, None, "previous", False, mx)
    rest = issue - issue % HOUR
    if rest >= end:
        return None
    run = data.newest_run(model, issue, rest, end)
    if run is None:
        return None
    _, temps = run.values(rest, end)
    model_max = float(temps.max())
    mso = data.max_so_far(target_day, issue)
    value = model_max if mso is None else max(model_max, float(mso))
    return RawForecast(model, value, run.run, "single", data.is_stale(model, run.run, issue), model_max, run)
