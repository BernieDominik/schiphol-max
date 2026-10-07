"""The target: rebuilt history, comparison with the KNMI official maximum, and the WU sample check (criterion 1)."""

from __future__ import annotations

import csv
import math
import random
from datetime import date, timedelta
from pathlib import Path

import numpy as np

from .access import Data
from .config import Config
from .timeutil import AMS, day_bounds, from_ts, season

WU_LINK = "https://www.wunderground.com/history/daily/nl/schiphol/EHAM/date/{y}-{m}-{d}"


def round_half_up(x: float) -> int:
    return int(math.floor(x + 0.5))


def max_time_local(data: Data, day: date) -> str | None:
    s, e = day_bounds(day)
    i, j = np.searchsorted(data.report_obs, [s, e])
    if j <= i:
        return None
    k = i + int(np.argmax(data.report_temp[i:j]))
    return from_ts(int(data.report_obs[k])).astimezone(AMS).strftime("%H:%M")


def target_vs_knmi(cfg: Config, data: Data) -> str:
    """By month: how often the rebuilt target differs from the rounded KNMI official maximum."""
    rows = {}
    for day, (value, _, _) in data.rebuilt.items():
        k = data.knmi.get(day)
        if k is None:
            continue
        r = rows.setdefault(day.month, {"n": 0, "same": 0, "lower": 0, "higher": 0, "last_hour": 0})
        diff = value - round_half_up(k[0])
        r["n"] += 1
        r["same"] += diff == 0
        r["lower"] += diff < 0
        r["higher"] += diff > 0
        r["last_hour"] += k[1] == 24
    out = cfg.reports_dir / "target_vs_knmi.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["month", "days", "same_as_knmi_rounded", "rebuilt_lower", "rebuilt_higher", "knmi_max_in_last_utc_hour"])
        for m in sorted(rows):
            r = rows[m]
            w.writerow([m, r["n"], r["same"], r["lower"], r["higher"], r["last_hour"]])
    lines = ["| Month | Days | Same as KNMI (rounded) | Rebuilt lower | Rebuilt higher | KNMI max in last UTC hour |",
             "| --- | --- | --- | --- | --- | --- |"]
    for m in sorted(rows):
        r = rows[m]
        lines.append(f"| {m} | {r['n']} | {r['same'] / r['n']:.0%} | {r['lower'] / r['n']:.0%} | {r['higher'] / r['n']:.0%} | "
                     f"{r['last_hour'] / r['n']:.1%} |")
    return "\n".join(lines)


def make_check_sheet(cfg: Config, data: Data, seed: int = 20261007, n_per_season: int = 15, n_odd: int = 12) -> Path:
    """60 sample days for criterion 1: 15 per season, at least 10 whose maximum came before 09:00 or after 20:00."""
    rng = random.Random(seed)
    first = date(2014, 1, 1)
    days = [d for d in sorted(data.rebuilt) if d >= first and d < data.wu_from]
    odd, normal = {s: [] for s in "DJF MAM JJA SON".split()}, {s: [] for s in "DJF MAM JJA SON".split()}
    for d in days:
        t = max_time_local(data, d)
        (odd if t and (t < "09:00" or t >= "20:00") else normal)[season(d)].append((d, t))
    picks = []
    for s in odd:
        k = n_odd // 4
        picks += rng.sample(odd[s], k) + rng.sample(normal[s], n_per_season - k)
    picks.sort()
    # The sheet to fill in is blind: it shows no rebuilt values, so they cannot steer the reading.
    path = cfg.reports_dir / "wu_check_sheet.csv"
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["date", "wu_link", "wu_max_c"])
        for d, _ in picks:
            w.writerow([d.isoformat(), WU_LINK.format(y=d.year, m=d.month, d=d.day), ""])
    with open(cfg.reports_dir / "wu_check_key.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["date", "season", "rebuilt_max_c", "max_time_local", "reports_that_day", "knmi_tx_c"])
        for d, t in picks:
            w.writerow([d.isoformat(), season(d), data.rebuilt[d][0], t, data.rebuilt[d][2], data.knmi.get(d, (None,))[0]])
    return path


def check_sheet(cfg: Config, data: Data, path: Path) -> dict:
    rows = list(csv.DictReader(open(path)))
    filled = [r for r in rows if r["wu_max_c"].strip()]
    agree = [r for r in filled if int(r["wu_max_c"]) == data.rebuilt[date.fromisoformat(r["date"])][0]]
    mismatches = [r for r in filled if r not in agree]
    return {"filled": len(filled), "agree": len(agree), "pass": len(filled) == 60 and len(agree) >= 57,
            "mismatches": [(r["date"], data.rebuilt[date.fromisoformat(r["date"])][0], r["wu_max_c"],
                            max_time_local(data, date.fromisoformat(r["date"]))) for r in mismatches]}


__all__ = ["target_vs_knmi", "make_check_sheet", "check_sheet", "round_half_up", "timedelta"]
