"""Write-once stores for forecast records, outcome records and fitted parameters (J1, I4).

Forecasts: records/forecasts/YYYY/MM/DD/<run>.json   (one file per run, DD = issue day, Amsterdam)
Outcomes:  records/outcomes/YYYY/MM/DD/<run>_l<lead>.json   (one file per forecast record, DD = target day)
Params:    params/YYYY/MM/DD/params_<HHMM>.json   (one file per refit, effective from its timestamp)
"""

from __future__ import annotations

import hashlib
import json
from bisect import bisect_left, bisect_right
from datetime import date
from pathlib import Path

from .config import Config
from .rawstore import read_json, write_once
from .timeutil import from_ts, local_date, parse_ts, AMS

Key = tuple[str, int]


def dumps(obj) -> str:
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False)


def content_hash(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True).encode()).hexdigest()[:12]


class RecordStore:
    def __init__(self, cfg: Config, load: bool = True):
        self.cfg = cfg
        self.base = cfg.records_dir
        # per key: parallel lists sorted by target day
        self.by_key: dict[Key, dict[str, list]] = {}
        self.by_day: dict[date, list[tuple[int, float]]] = {}    # target day -> [(issue, mu)]
        self.outcomes: dict[tuple[Key, date], dict] = {}
        self.files: set[str] = set()
        if load:
            self._load()

    # ------------------------------------------------------------ paths

    def forecast_path(self, run: str, issue: int) -> Path:
        d = local_date(issue)
        return self.base / "forecasts" / f"{d:%Y/%m/%d}" / f"{run}.json"

    def outcome_path(self, key: Key, day: date) -> Path:
        return self.base / "outcomes" / f"{day:%Y/%m/%d}" / f"{key[0]}_l{key[1]}.json"

    def has_forecast(self, run: str, issue: int) -> bool:
        return self.forecast_path(run, issue).exists()

    # ------------------------------------------------------------ loading

    def _load(self) -> None:
        fdir = self.base / "forecasts"
        if fdir.exists():
            for p in sorted(fdir.rglob("*.json")):
                self._index_file(read_json(p))
        odir = self.base / "outcomes"
        if odir.exists():
            for p in sorted(odir.rglob("*.json")):
                o = read_json(p)
                self.outcomes[((o["run"], o["lead"]), date.fromisoformat(o["target_day"]))] = o

    def _index_file(self, f: dict) -> None:
        for rec in f["records"]:
            self.add(rec, f.get("baselines_by_day", {}).get(rec["target_day"]))

    def add(self, rec: dict, baselines: list | None = None) -> None:
        key = (rec["run"], rec["lead"])
        day = date.fromisoformat(rec["target_day"])
        k = self.by_key.setdefault(key, {"ord": [], "rec": [], "issue": [], "base": []})
        i = bisect_right(k["ord"], day.toordinal())
        k["ord"].insert(i, day.toordinal())
        k["rec"].insert(i, rec)
        k["issue"].insert(i, parse_ts(rec["issued_at_utc"]))
        k["base"].insert(i, baselines or [])
        self.by_day.setdefault(day, []).append((parse_ts(rec["issued_at_utc"]), rec["mu"]))

    # ------------------------------------------------------------ writing

    def write_forecast(self, run: str, issue: int, payload: dict) -> bool:
        if not write_once(self.forecast_path(run, issue), payload, sort_keys=False):
            return False
        for rec in payload["records"]:
            self.add(rec, payload.get("baselines_by_day", {}).get(rec["target_day"]))
        return True

    def write_outcome(self, key: Key, day: date, payload: dict) -> bool:
        if not write_once(self.outcome_path(key, day), payload, sort_keys=False):
            return False
        self.outcomes[(key, day)] = payload
        return True

    # ------------------------------------------------------------ queries (all filtered by time)

    def window(self, key: Key, first_ord: int, last_ord: int) -> range:
        k = self.by_key.get(key)
        if not k:
            return range(0)
        return range(bisect_left(k["ord"], first_ord), bisect_left(k["ord"], last_ord))

    def records(self, key: Key) -> dict[str, list]:
        return self.by_key.get(key, {"ord": [], "rec": [], "issue": [], "base": []})

    def previous_mu(self, day: date, issue: int) -> float | None:
        earlier = [(t, mu) for t, mu in self.by_day.get(day, []) if t < issue]
        return max(earlier)[1] if earlier else None

    def typical_p_miss(self, key: Key, issue: int, days: int) -> float | None:
        k = self.records(key)
        lo = bisect_left(k["issue"], issue - days * 86400) if k["issue"] else 0
        vals = [k["rec"][i]["p_miss_2_or_more"] for i in range(lo, len(k["rec"])) if k["issue"][i] < issue]
        return round(sum(vals) / len(vals), 4) if vals else None

    def unsettled(self) -> list[tuple[Key, date, dict, list]]:
        out = []
        for key, k in self.by_key.items():
            for o, rec, base in zip(k["ord"], k["rec"], k["base"]):
                day = date.fromordinal(o)
                if (key, day) not in self.outcomes:
                    out.append((key, day, rec, base))
        return out


class ParamStore:
    def __init__(self, cfg: Config, load: bool = True):
        self.cfg = cfg
        self.base = cfg.params_dir
        self.items: list[tuple[int, dict]] = []
        if load and self.base.exists():
            for p in sorted(self.base.rglob("params_*.json")):
                d = read_json(p)
                self.items.append((parse_ts(d["effective_from_utc"]), d))
        self.items.sort(key=lambda x: x[0])
        self._eff = [t for t, _ in self.items]

    def path(self, effective: int) -> Path:
        local = from_ts(effective).astimezone(AMS)
        return self.base / f"{local:%Y/%m/%d}" / f"params_{local:%H%M}.json"

    def at(self, ts: int) -> dict | None:
        i = bisect_right(self._eff, ts)
        return self.items[i - 1][1] if i else None

    def has(self, effective: int) -> bool:
        return effective in self._eff

    def save(self, params: dict) -> None:
        eff = parse_ts(params["effective_from_utc"])
        write_once(self.path(eff), params)
        if eff not in self._eff:
            i = bisect_right(self._eff, eff)
            self._eff.insert(i, eff)
            self.items.insert(i, (eff, params))
