"""Criterion 9: re-running any stored forecast from raw data and stored parameters gives the identical record."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from .engine import Ctx, forecast_day
from .schedule import target_days
from .timeutil import local_date, parse_ts

IGNORED = {"produced_at_utc", "mode"}


def reproduce_file(ctx: Ctx, path: Path) -> list[str]:
    """Differences between a stored forecast file and a fresh re-run (empty list = identical)."""
    f = json.loads(path.read_text())
    issue = parse_ts(f["issued_at_utc"])
    P = next((p for t, p in ctx.params.items if p["effective_from_utc"] == f["parameter_version"]), None)
    if P is None:
        return [f"{path.name}: parameter set {f['parameter_version']} not found"]
    diffs = []
    stored = {r["target_day"]: r for r in f["records"]}
    for lead, day in target_days(ctx.cfg, f["run"], local_date(issue)):
        out = forecast_day(ctx, f["run"], lead, day, issue, P)
        old = stored.get(day.isoformat())
        if out is None and old is None:
            continue
        if out is None or old is None:
            diffs.append(f"{path}: {day} present in only one of stored/re-run")
            continue
        new, base = out
        if new != old:
            keys = [k for k in new if new.get(k) != old.get(k)]
            diffs.append(f"{path}: {day} differs in {keys}")
        if base != f["baselines_by_day"].get(day.isoformat(), []):
            diffs.append(f"{path}: {day} baselines differ")
    return diffs


def reproduce_day(ctx: Ctx, day: date) -> list[str]:
    base = ctx.cfg.records_dir / "forecasts" / f"{day:%Y/%m/%d}"
    diffs = []
    for p in sorted(base.glob("*.json")) if base.exists() else []:
        diffs += reproduce_file(ctx, p)
    return diffs


def reproduce_range(ctx: Ctx, start: date, end: date, log=print) -> tuple[int, list[str]]:
    n, diffs = 0, []
    base = ctx.cfg.records_dir / "forecasts"
    for p in sorted(base.rglob("*.json")):
        d = date.fromisoformat("-".join(p.parts[-4:-1]))
        if start <= d <= end:
            diffs += reproduce_file(ctx, p)
            n += 1
    log(f"re-ran {n} forecast files, {len(diffs)} differences")
    return n, diffs
