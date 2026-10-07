"""The only way forecasting code reads data (PRD coding rule).

Every value carries `available`: the moment its source published it (never the moment we fetched it).
Every query takes an `issue` time and returns nothing that became available after it, so a forecast
made late, in a backtest, or re-run next year sees exactly the same inputs.
"""

from __future__ import annotations

import sqlite3
from bisect import bisect_right
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

import numpy as np

from .config import Config
from .derived import connect
from .timeutil import HOUR, UTC, day_bounds, from_ts, local_date, to_date, to_ts


@dataclass
class Run:
    model: str
    run: int
    available: int
    valid: np.ndarray            # UTC hour starts, sorted
    temp: np.ndarray

    def covers(self, start: int, end: int) -> bool:
        """True if every whole hour in [start, end) has a value."""
        n = (end - start) // HOUR
        i = int(np.searchsorted(self.valid, start))
        if i + n > len(self.valid):
            return False
        return bool(self.valid[i] == start and self.valid[i + n - 1] == end - HOUR)

    def values(self, start: int, end: int) -> tuple[np.ndarray, np.ndarray]:
        i, j = np.searchsorted(self.valid, [start, end])
        return self.valid[i:j], self.temp[i:j]


@dataclass
class ModelSeries:
    runs: list[Run] = field(default_factory=list)          # sorted by run time
    run_times: list[int] = field(default_factory=list)
    prev_valid: np.ndarray | None = None                   # sorted valid hours
    prev_temp: np.ndarray | None = None                    # shape (len(prev_valid), 8): days 0..7
    unavailable: set[int] = field(default_factory=set)     # runs the archive said do not exist


@dataclass
class Report:
    obs: int
    temp: int
    available: int


class Data:
    """In-memory view of the derived store with availability-aware queries."""

    def __init__(self, cfg: Config, con: sqlite3.Connection | None = None):
        self.cfg = cfg
        own = con is None
        con = con or connect(cfg)
        self.margin = cfg["collection"]["publish_margin_minutes"] * 60
        self.metar_delay = cfg["collection"]["metar_delay_minutes"] * 60
        self._load_publish(con)
        self._load_models(con)
        self._load_metar(con)
        self._load_targets(con)
        self._load_misc(con)
        if own:
            con.close()

    # ------------------------------------------------------------ loading

    def _load_publish(self, con) -> None:
        self.published: dict[tuple[str, int], int] = {}
        for model, run, pub in con.execute("SELECT model, run, min(published) FROM publish GROUP BY model, run"):
            self.published[(model, run)] = pub
        # 95th-percentile publishing delay per model and run hour, from measured publish times.
        self.delay: dict[tuple[str, int], int] = {}
        by_model: dict[str, list[int]] = {}
        by_hour: dict[tuple[str, int], list[int]] = {}
        for (model, run), pub in self.published.items():
            d = pub - run
            if 0 < d < 48 * HOUR:
                by_model.setdefault(model, []).append(d)
                by_hour.setdefault((model, from_ts(run).hour), []).append(d)
        for name, spec in self.cfg.models.items():
            model_p95 = int(np.percentile(by_model[name], 95)) if len(by_model.get(name, [])) >= 10 else None
            hours = range(24) if spec.previous_run_every_h == 1 else range(0, 24, 3)
            for h in hours:
                vals = by_hour.get((name, h), [])
                if len(vals) >= 10:
                    self.delay[(name, h)] = int(np.percentile(vals, 95))
                elif model_p95 is not None:
                    self.delay[(name, h)] = model_p95
                else:
                    self.delay[(name, h)] = int(spec.delay_h * HOUR)

    def run_available(self, model: str, run: int) -> int:
        pub = self.published.get((model, run))
        if pub is None:
            pub = run + self.delay.get((model, from_ts(run).hour), int(self.cfg.models[model].delay_h * HOUR))
        return pub + self.margin

    def _load_models(self, con) -> None:
        self.models: dict[str, ModelSeries] = {m: ModelSeries() for m in self.cfg.models}
        rows = con.execute("SELECT model, run, valid, temp FROM single_hourly ORDER BY model, run, valid").fetchall()
        if rows:
            arr = np.array([(r[1], r[2], r[3]) for r in rows], dtype=float)
            models = [r[0] for r in rows]
            start = 0
            for i in range(1, len(rows) + 1):
                if i == len(rows) or models[i] != models[start] or arr[i, 0] != arr[start, 0]:
                    m, run = models[start], int(arr[start, 0])
                    if m in self.models:
                        self.models[m].runs.append(Run(m, run, self.run_available(m, run),
                                                       arr[start:i, 1].astype(np.int64), arr[start:i, 2]))
                    start = i
        for ms in self.models.values():
            ms.runs.sort(key=lambda r: r.run)
            ms.run_times = [r.run for r in ms.runs]
        for model, run in con.execute("SELECT model, run FROM single_run WHERE status='unavailable'"):
            if model in self.models:
                self.models[model].unavailable.add(run)
        for m in self.models:
            prev = con.execute("SELECT valid, n, temp FROM prev_hourly WHERE model=? ORDER BY valid", (m,)).fetchall()
            if not prev:
                continue
            valid = np.array(sorted({r[0] for r in prev}), dtype=np.int64)
            mat = np.full((len(valid), 8), np.nan)
            idx = {v: i for i, v in enumerate(valid.tolist())}
            for v, n, t in prev:
                mat[idx[v], n] = t
            self.models[m].prev_valid, self.models[m].prev_temp = valid, mat

    def _load_metar(self, con) -> None:
        by_obs: dict[int, list[tuple[str, int | None, int | None]]] = {}
        for obs, report, temp, receipt in con.execute("SELECT obs, report, temp, receipt FROM metar ORDER BY obs"):
            by_obs.setdefault(obs, []).append((report, temp, receipt))
        reports = []
        for obs, items in by_obs.items():
            cor = [it for it in items if " COR " in f" {it[0]} "]
            chosen = cor or items
            temps = [t for _, t, _ in chosen if t is not None]
            if not temps:
                continue
            receipts = [r for _, _, r in items if r is not None]
            available = max(obs + self.metar_delay, min(receipts)) if receipts else obs + self.metar_delay
            reports.append(Report(obs, max(temps), available))
        self.reports = reports
        self.report_obs = np.array([r.obs for r in reports], dtype=np.int64)
        self.report_temp = np.array([r.temp for r in reports], dtype=float)
        self.report_avail = np.array([r.available for r in reports], dtype=np.int64)

    def _load_targets(self, con) -> None:
        """Target values: the maximum rebuilt from airport reports (history) and hand-entered WU values."""
        self.rebuilt: dict[date, tuple[int, int, int]] = {}   # day -> (value, available, n_reports)
        if len(self.report_obs):
            first = max(local_date(int(self.report_obs[0])), to_date(self.cfg["target"]["history_from"]))
            last = local_date(int(self.report_obs[-1]))
            d = first
            while d <= last:
                s, e = day_bounds(d)
                i, j = np.searchsorted(self.report_obs, [s, e])
                if j > i and j < len(self.report_obs):
                    value = int(self.report_temp[i:j].max())
                    # Final once the first report of the next day is out (PRD target rule 2).
                    self.rebuilt[d] = (value, int(self.report_avail[j]), j - i)
                d += timedelta(days=1)
        self.wu: dict[date, tuple[int, int]] = {}
        for day, value, entered in con.execute("SELECT day, value, entered_at FROM wu ORDER BY entered_at"):
            self.wu.setdefault(date.fromisoformat(day), (value, entered))  # the first entry is final
        self.wu_from = to_date(self.cfg["live"]["wu_from"])

    def _load_misc(self, con) -> None:
        self.knmi = {date.fromisoformat(d): (tx, txh) for d, tx, txh in con.execute("SELECT day, tx, txh FROM knmi")}
        self.mosmix: dict[int, dict] = {}
        for issue, valid, ttt, tx, pub in con.execute("SELECT issue, valid, ttt, tx, published FROM mosmix ORDER BY issue, valid"):
            m = self.mosmix.setdefault(issue, {"published": pub, "valid": [], "ttt": [], "tx": []})
            m["valid"].append(valid)
            m["ttt"].append(ttt)
            m["tx"].append(tx)

    # ------------------------------------------------------------ queries

    def target(self, day: date, as_of: int | None = None) -> tuple[int, str, int] | None:
        """(value, source, available) of the target for `day`, if known by `as_of`."""
        if day >= self.wu_from:
            hit = self.wu.get(day)
            src = "wu"
        else:
            hit = self.rebuilt.get(day)
            src = "rebuilt"
            hit = (hit[0], hit[1]) if hit else None
        if hit is None or (as_of is not None and hit[1] > as_of):
            return None
        return hit[0], src, hit[1]

    def newest_run(self, model: str, issue: int, start: int, end: int, max_back: int = 24) -> Run | None:
        """Newest exact run published before `issue` that covers every hour of [start, end)."""
        ms = self.models[model]
        k = bisect_right(ms.run_times, issue)
        for run in reversed(ms.runs[max(0, k - max_back):k]):
            if run.available <= issue and run.covers(start, end):
                return run
        return None

    def is_stale(self, model: str, used_run: int, issue: int) -> bool:
        """True when a newer scheduled run should normally have been out by `issue` but was not used."""
        spec = self.cfg.models[model]
        t = issue - issue % HOUR
        while t > used_run:
            h = from_ts(t).hour
            if h in spec.run_hours:
                expected = t + self.delay.get((model, h), int(spec.delay_h * HOUR)) + self.margin
                if expected <= issue:
                    return True
            t -= HOUR
        return False

    def prev_source_run(self, model: str, valid: int, n: int) -> int:
        """Run assumed to have produced the 'n days before' value for `valid`: the newest *scheduled* run started
        at or before valid − 24·n h. That is at least as new as the true one (verified against exact runs), so
        the availability we assume is never earlier than reality."""
        spec = self.cfg.models[model]
        latest = valid - 24 * n * HOUR
        if spec.previous_run_every_h == 1:
            return latest - latest % HOUR
        src = latest - latest % (3 * HOUR)
        while from_ts(src).hour not in spec.run_hours:
            src -= 3 * HOUR
        return src

    def previous_runs_hours(self, model: str, hours: list[int], issue: int) -> np.ndarray | None:
        """Day-ahead archive, hour by hour, using only values whose producing run was out by `issue`
        (the smallest 'days before' whose run had been published)."""
        ms = self.models[model]
        if ms.prev_valid is None:
            return None
        out = np.empty(len(hours))
        for i, t in enumerate(hours):
            j = int(np.searchsorted(ms.prev_valid, t))
            if j >= len(ms.prev_valid) or ms.prev_valid[j] != t:
                return None
            row = ms.prev_temp[j]
            for n in range(1, 8):
                if not np.isnan(row[n]) and self.run_available(model, self.prev_source_run(model, t, n)) <= issue:
                    out[i] = row[n]
                    break
            else:
                return None
        return out

    def reports_between(self, start: int, end: int, issue: int) -> tuple[np.ndarray, np.ndarray]:
        i, j = np.searchsorted(self.report_obs, [start, end])
        mask = self.report_avail[i:j] <= issue
        return self.report_obs[i:j][mask], self.report_temp[i:j][mask]

    def max_so_far(self, day: date, issue: int) -> int | None:
        s, _ = day_bounds(day)
        _, temps = self.reports_between(s, issue, issue)
        return int(temps.max()) if len(temps) else None

    def mosmix_max(self, day: date, issue: int) -> float | None:
        """MOSMIX full-day maximum for an Amsterdam day: TX at 18 UTC (covers 06–18 UTC) combined with the
        hourly TTT outside that window (PRD open question 8)."""
        best = None
        for iss in sorted(self.mosmix, reverse=True):
            if self.mosmix[iss]["published"] <= issue:
                best = self.mosmix[iss]
                break
        if best is None:
            return None
        s, e = day_bounds(day)
        valid = np.array(best["valid"])
        ttt = np.array([np.nan if v is None else v for v in best["ttt"]], dtype=float)
        tx = np.array([np.nan if v is None else v for v in best["tx"]], dtype=float)
        in_day = (valid >= s) & (valid < e)
        if not in_day.any() or valid[in_day].min() > s:
            return None
        t18 = to_ts(datetime(day.year, day.month, day.day, 18, tzinfo=UTC))
        hrs = valid[in_day]
        window = (hrs > t18 - 12 * HOUR) & (hrs <= t18)
        cand = list(ttt[in_day][~window])
        k = np.where(valid == t18)[0]
        if len(k) and not np.isnan(tx[k[0]]):
            cand.append(tx[k[0]])
        else:
            cand += list(ttt[in_day][window])
        cand = [c for c in cand if not np.isnan(c)]
        return float(max(cand)) if cand else None
