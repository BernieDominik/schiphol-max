"""`smax tick`: the one scheduled entry point. GitHub runs it every hour; it does whatever is due.

Order: collect → ingest → refit / forecast / settle for every due slot (including slots missed in the
last 72 h) → nightly re-run check → completeness report → weekly scorecard → reminders → FORECAST.md.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta

from .alerts import Journal, load_state, save_state
from .config import Config
from .derived import connect, rebuild
from .schedule import slots_between
from .timeutil import AMS, UTC, local_date, local_ts, to_ts


def _collect(cfg: Config, j: Journal, now: datetime, state: dict) -> None:
    from .collect import knmi, metar, mosmix, openmeteo
    from .net import Http

    http = Http(cfg)
    ok, latest = j.run("latest_runs", openmeteo.record_latest_runs, cfg, http, now, alert=False)
    local = now.astimezone(AMS)
    jobs = {
        "single_runs": lambda: openmeteo.catch_up_single_runs(cfg, http, now, latest or {}),
        "awc_metar": lambda: metar.collect_awc(cfg, http, now),
        "mosmix": lambda: mosmix.collect_mosmix(cfg, http),
        "publish_times": lambda: [openmeteo.collect_publish_times(cfg, http, now.date() - timedelta(days=k)) for k in (1, 2)],
    }
    if local.hour >= 3:
        jobs["iem_metar"] = lambda: metar.collect_iem_recent(cfg, http, now)
    if local.hour >= 7:
        jobs["knmi_daily"] = lambda: knmi.collect_knmi_recent(cfg, http, local.date())
    if local.hour >= 20:
        jobs["ensemble"] = lambda: openmeteo.collect_ensemble(cfg, http, local.date())
    results = {"latest_runs": ok}
    for name, fn in jobs.items():
        results[name], _ = j.run(name, fn, alert=False)
    for name, good in results.items():
        fails = 0 if good else state.get(name, 0) + 1
        state[name] = fails
        if fails >= 2:
            j.alert(f"source {name} failed {fails} times in a row")


def tick(cfg: Config, now: datetime | None = None, dry_run: bool = False, collect: bool = True) -> int:
    now = now or datetime.now(UTC)
    now_ts = to_ts(now)
    j = Journal(cfg)
    state = load_state(cfg)
    live_runs = list(cfg["live"]["runs"])
    sch = cfg["schedule"]
    due = slots_between(cfg, now_ts - sch["catch_up_hours"] * 3600, now_ts, live_runs)

    if dry_run:
        for s in due:
            print(f"{s.name:<22} {datetime.fromtimestamp(s.ts, AMS):%Y-%m-%d %H:%M %Z}")
        return 0

    if collect:
        _collect(cfg, j, now, state)
    j.run("ingest", rebuild, cfg)

    from .engine import build_ctx, forecast_slot, settle
    from .params import refit
    from .store import ParamStore, RecordStore

    store, params = RecordStore(cfg), ParamStore(cfg)
    todo_refit = [s for s in due if s.kind == "refit" and not params.has(s.ts)]
    todo_fc = [s for s in due if s.kind == "forecast" and not store.has_forecast(s.run, s.ts)]
    ctx = None

    def get_ctx():
        nonlocal ctx
        if ctx is None:
            ctx = build_ctx(cfg, last_day=local_date(now_ts) + timedelta(days=9), log=lambda m: j.log("engine", "note", m))
        return ctx

    for s in sorted(todo_refit + todo_fc):
        if s.kind == "refit":
            j.run(f"refit {s.day}", refit, get_ctx(), s.ts)
        else:
            j.run(f"forecast {s.run} {s.day}", forecast_slot, get_ctx(), s.run, s.ts, now_ts, "live")
    today = local_date(now_ts)
    if ctx is not None or any(day < today for _, day, _, _ in store.unsettled()):
        j.run("settle", settle, get_ctx(), now_ts, now_ts)

    # Nightly: re-run yesterday's records from raw data and stored parameters; any difference is an alert.
    nightly = [s for s in due if s.kind == "settle" and s.day == local_date(now_ts)]
    marker = cfg.root / "data" / "state" / f"reproduced_{local_date(now_ts)}"
    if nightly and not marker.exists():
        from .reproduce import reproduce_day
        ok, diffs = j.run("reproduce", reproduce_day, get_ctx(), local_date(now_ts) - timedelta(days=1))
        if ok and diffs:
            j.alert(f"re-run differs from stored records: {diffs[:3]}")
        if ok:
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text("ok\n")

    # Daily completeness report for yesterday (A6).
    if now.astimezone(AMS).hour >= 7:
        day = local_date(now_ts) - timedelta(days=1)
        path = cfg.reports_dir / "completeness" / f"{day.isoformat()}.md"
        if not path.exists():
            from .completeness import completeness
            con = connect(cfg)
            ok, out = j.run("completeness", completeness, cfg, con, RecordStore(cfg), day, live_runs)
            con.close()
            if ok:
                text, problems = out
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text)
                if problems:
                    j.alert(f"completeness {day}: " + "; ".join(problems[:5]))

    # Weekly scorecard (J3).
    for s in due:
        if s.kind == "scorecard":
            path = cfg.reports_dir / "scorecards" / f"{s.day.isoformat()}.md"
            if not path.exists():
                from .score import weekly_scorecard
                j.run("scorecard", weekly_scorecard, cfg, path)

    # Reminder: hand-entered Weather Underground values.
    from .access import Data
    wu_from = date.fromisoformat(cfg["live"]["wu_from"])
    if ctx is not None:
        data = ctx.data
    else:
        data = None
    remind_before = local_date(now_ts) - timedelta(days=cfg["target"]["wu_reminder_days"])
    if remind_before >= wu_from:
        data = data or Data(cfg)
        missing = [d for d in (wu_from + timedelta(days=i) for i in range((remind_before - wu_from).days + 1)) if d not in data.wu]
        if missing:
            j.alert(f"Weather Underground maximum not entered for: {', '.join(d.isoformat() for d in missing[:10])}")

    j.run("forecast page", write_forecast_page, cfg)
    save_state(cfg, state)
    return j.finish()


def write_forecast_page(cfg: Config) -> str:
    from .record import forecast_page
    base = cfg.records_dir / "forecasts"
    files = sorted(base.rglob("*.json"), key=lambda p: (p.parent, p.name))[-12:] if base.exists() else []
    newest: dict[str, dict] = {}
    latest_evening = None
    for p in files:
        f = json.loads(p.read_text())
        for rec in f["records"]:
            cur = newest.get(rec["target_day"])
            if cur is None or rec["issued_at_utc"] > cur["issued_at_utc"]:
                newest[rec["target_day"]] = rec
        if f["run"] == "evening" and (latest_evening is None or f["issued_at_utc"] > latest_evening["issued_at_utc"]):
            latest_evening = f
    today = datetime.now(AMS).date().isoformat()
    upcoming = [newest[d] for d in sorted(newest) if d >= today][:2]
    outlook = [r for r in (latest_evening or {}).get("records", []) if r["lead"] >= 2]
    page = forecast_page(upcoming, outlook)
    (cfg.root / "FORECAST.md").write_text(page)
    return f"{len(upcoming)} days"


__all__ = ["tick", "write_forecast_page", "local_ts"]
