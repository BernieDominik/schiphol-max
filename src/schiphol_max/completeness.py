"""A6: the daily completeness report: every expected fetch and scheduled run, and what is missing."""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta

from .config import Config
from .schedule import slots_between
from .store import RecordStore
from .timeutil import day_bounds, from_ts, iso_z


def completeness(cfg: Config, con: sqlite3.Connection, store: RecordStore, day: date,
                 live_runs: list[str]) -> tuple[str, list[str], list[str]]:
    """Markdown report for one Amsterdam day, our collection problems (gaps we caused, which break the soak) and
    warnings (gaps at the source: a report the airport never sent, KNMI's service closing)."""
    s, e = day_bounds(day)
    problems, warnings, lines = [], [], [f"# Completeness {day.isoformat()}", ""]

    lines += ["## Model runs (exact-run archive)", "", "| Model | Expected | Stored | Not in archive | Missing |", "| --- | --- | --- | --- | --- |"]
    for name, spec in cfg.models.items():
        expected = [t for t in range(s - s % 3600, e, 3600) if from_ts(t).hour in spec.run_hours and t >= s]
        rows = dict(con.execute("SELECT run, status FROM single_run WHERE model=? AND run>=? AND run<?", (name, s, e)).fetchall())
        ok = sum(1 for t in expected if rows.get(t) == "ok")
        unavailable = sum(1 for t in expected if rows.get(t) == "unavailable")
        missing = [t for t in expected if t not in rows]
        lines.append(f"| {name} | {len(expected)} | {ok} | {unavailable} | {len(missing)} |")
        if missing:
            problems.append(f"{name}: {len(missing)} runs never fetched ({', '.join(iso_z(t)[11:16] for t in missing)})")

    n_reports = con.execute("SELECT count(DISTINCT obs) FROM metar WHERE obs>=? AND obs<?", (s, e)).fetchone()[0]
    expected_reports = (e - s) // 1800
    lines += ["", f"Airport reports: {n_reports} of {expected_reports} half-hourly slots."]
    if n_reports < expected_reports - 4:
        warnings.append(f"airport reports: only {n_reports} of {expected_reports} (source side)")

    n_mosmix = con.execute("SELECT count(DISTINCT issue) FROM mosmix WHERE issue>=? AND issue<?", (s, e)).fetchone()[0]
    lines.append(f"MOSMIX runs: {n_mosmix} of 4.")
    if n_mosmix < 4:
        problems.append(f"MOSMIX: {n_mosmix} of 4 runs saved")

    last_knmi = con.execute("SELECT max(day) FROM knmi").fetchone()[0]
    lines.append(f"Latest KNMI daily value: {last_knmi}.")
    if last_knmi is None or date.fromisoformat(last_knmi) < day - timedelta(days=4):
        warnings.append(f"KNMI daily data stale (latest {last_knmi}); reference series only")

    lines += ["", "## Scheduled forecast runs", "", "| Run | Issued | Status |", "| --- | --- | --- |"]
    for slot in slots_between(cfg, s - 1, e - 1, live_runs):
        if slot.kind != "forecast":
            continue
        path = store.forecast_path(slot.run, slot.ts)
        if path.exists():
            import json
            mode = json.loads(path.read_text()).get("mode")
            status = "on time" if mode == "live" else mode
            if mode == "late":
                problems.append(f"forecast {slot.run} {day} was produced late")
        else:
            status = "MISSING"
            problems.append(f"forecast {slot.run} {day} missing")
        lines.append(f"| {slot.run} | {iso_z(slot.ts)} | {status} |")

    lines += ["", "## Problems (our collection)", ""] + ([f"- {p}" for p in problems] or ["None."])
    lines += ["", "## Warnings (source side)", ""] + ([f"- {w}" for w in warnings] or ["None."])
    return "\n".join(lines) + "\n", problems, warnings
