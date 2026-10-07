"""The daily schedule (Europe/Amsterdam time) as a list of slots. Live running and backtests walk the same slots."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from .config import Config
from .timeutil import local_date, local_ts

KIND_ORDER = {"settle": 0, "refit": 1, "forecast": 2, "completeness": 3, "scorecard": 4}


@dataclass(frozen=True, order=True)
class Slot:
    ts: int
    order: int
    kind: str = field(compare=False)
    run: str = field(default="", compare=False)
    day: date = field(default=None, compare=False)   # local date of the slot

    @property
    def name(self) -> str:
        return f"{self.kind}:{self.run}" if self.run else self.kind


def run_names(cfg: Config) -> list[str]:
    return list(cfg["schedule"]["forecast_runs"])


def leads(cfg: Config, run: str) -> list[int]:
    return list(cfg["schedule"]["forecast_runs"][run]["leads"])


def keys(cfg: Config) -> list[tuple[str, int]]:
    """Every (run, lead) combination; corrections, weights and spreads are kept per key."""
    return [(r, l) for r in run_names(cfg) for l in leads(cfg, r)]


def issue_time(cfg: Config, run: str, lead: int, target_day: date) -> int:
    t = cfg["schedule"]["forecast_runs"][run]["time"]
    if lead == 0:
        return local_ts(target_day, t)
    return local_ts(target_day - timedelta(days=lead), t)


def target_days(cfg: Config, run: str, issue_day: date) -> list[tuple[int, date]]:
    return [(l, issue_day + timedelta(days=l)) for l in leads(cfg, run)]


def slots_between(cfg: Config, start: int, end: int, runs: list[str] | None = None) -> list[Slot]:
    """All slots with start < ts <= end, in time order."""
    sch = cfg["schedule"]
    runs = run_names(cfg) if runs is None else runs
    out: list[Slot] = []
    d = local_date(start) - timedelta(days=1)
    last = local_date(end) + timedelta(days=1)
    while d <= last:
        cand = [Slot(local_ts(d, sch["settle"]), KIND_ORDER["settle"], "settle", "", d),
                Slot(local_ts(d, sch["completeness"]), KIND_ORDER["completeness"], "completeness", "", d)]
        if d.weekday() == sch["refit"]["weekday"]:
            cand.append(Slot(local_ts(d, sch["refit"]["time"]), KIND_ORDER["refit"], "refit", "", d))
        if d.weekday() == sch["scorecard"]["weekday"]:
            cand.append(Slot(local_ts(d, sch["scorecard"]["time"]), KIND_ORDER["scorecard"], "scorecard", "", d))
        for r in runs:
            cand.append(Slot(local_ts(d, sch["forecast_runs"][r]["time"]), KIND_ORDER["forecast"], "forecast", r, d))
        out += [s for s in cand if start < s.ts <= end]
        d += timedelta(days=1)
    return sorted(out)
