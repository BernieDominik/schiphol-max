"""`smax` command line: one command per scheduled job plus build and check tools."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from .config import load_config
from .timeutil import UTC, local_date, local_ts, parse_iso, to_ts


def _log(msg: str) -> None:
    print(f"[{datetime.now(UTC):%Y-%m-%d %H:%M:%S}Z] {msg}", flush=True)


def _cfg(args):
    cfg = load_config()
    overrides = {}
    for item in getattr(args, "set", None) or []:
        k, v = item.split("=", 1)
        try:
            overrides[k] = json.loads(v)
        except json.JSONDecodeError:
            overrides[k] = v
    data_dir = Path(args.dir).resolve() if getattr(args, "dir", None) else None
    if overrides or data_dir:
        cfg = cfg.with_overrides(overrides, data_dir=data_dir)
    return cfg


def cmd_backfill(args) -> int:
    from .collect import knmi, metar, openmeteo
    from .net import Http

    cfg = load_config()
    http = Http(cfg)
    today = datetime.now(UTC).date()
    what = set(args.what.split(","))
    if what & {"all", "knmi"}:
        knmi.backfill_knmi(cfg, http, today - timedelta(days=1), _log)
    if what & {"all", "iem"}:
        metar.backfill_iem(cfg, http, today - timedelta(days=1), _log)
    if what & {"all", "previous"}:
        openmeteo.backfill_previous_runs(cfg, http, today - timedelta(days=1), _log)
    if what & {"all", "publish"}:
        d = date.fromisoformat(args.publish_from)
        while d < today:
            openmeteo.collect_publish_times(cfg, http, d)
            d += timedelta(days=1)
        _log("publish times stored")
    if what & {"all", "single"}:
        end = to_ts(parse_iso(args.until)) if args.until else to_ts(datetime.now(UTC)) - 3 * 3600
        start = to_ts(parse_iso(args.single_from)) if args.single_from else 0
        openmeteo.backfill_single_runs(cfg, http, start, end, _log)
    _log("backfill done")
    return 0


def cmd_rebuild(args) -> int:
    from .derived import rebuild
    n = rebuild(load_config(), full=args.full, log=_log)
    _log(f"ingested {n} raw files")
    return 0


def cmd_tick(args) -> int:
    from .live import tick
    now = parse_iso(args.now) if args.now else None
    return tick(load_config(), now=now, dry_run=args.dry_run, collect=not args.no_collect)


def cmd_replay(args) -> int:
    """Walk-forward replay. Without --dir it extends the official record chain."""
    from .derived import rebuild
    from .engine import build_ctx, replay

    cfg = _cfg(args)
    rebuild(load_config())
    start_day = date.fromisoformat(args.start or cfg["live"]["chain_start"]) - timedelta(days=1)
    start = local_ts(start_day, "00:30")
    end = to_ts(parse_iso(args.end)) if args.end else to_ts(datetime.now(UTC))
    runs = args.runs.split(",") if args.runs else None
    ctx = build_ctx(cfg, last_day=local_date(end) + timedelta(days=9), variant=args.variant, log=_log)
    _log(f"replaying {start_day} → {datetime.fromtimestamp(end, UTC):%Y-%m-%d %H:%M}Z into {cfg.data_dir}")
    replay(ctx, start, end, runs)
    _log("replay done")
    return 0


def cmd_target(args) -> int:
    from .access import Data
    from .collect.wu import enter_wu_value
    from .derived import rebuild
    from . import target as T

    cfg = load_config()
    if args.action == "set":
        day, value = date.fromisoformat(args.day), int(args.value)
        rebuild(cfg)
        data = Data(cfg)
        if day in data.wu:
            print(f"{day} already has a recorded value ({data.wu[day][0]} °C). Recorded values are final.")
            return 1
        rebuilt = data.rebuilt.get(day)
        if rebuilt and abs(rebuilt[0] - value) > cfg["target"]["wu_max_gap_c"] and not args.confirm:
            print(f"{value} °C is more than {cfg['target']['wu_max_gap_c']} °C from the airport-report maximum "
                  f"({rebuilt[0]} °C). Check the page (°C, not °F) and repeat with --confirm if it is right.")
            return 1
        path = enter_wu_value(cfg, day, value, entered_by=args.by)
        print(f"recorded {day}: {value} °C ({path})")
        return 0
    rebuild(cfg)
    data = Data(cfg)
    if args.action == "sheet":
        print(T.make_check_sheet(cfg, data))
    elif args.action == "check":
        print(json.dumps(T.check_sheet(cfg, data, Path(args.day or cfg.reports_dir / "wu_check_sheet.csv")), indent=1))
    elif args.action == "knmi":
        print(T.target_vs_knmi(cfg, data))
    return 0


def cmd_baselines(args) -> int:
    from .access import Data
    from .baselines import criterion2
    print(json.dumps(criterion2(Data(load_config())), indent=1))
    return 0


def cmd_score(args) -> int:
    from .score import load_frames, scorecard, test_period
    cfg = _cfg(args)
    df, tab, base = load_frames(cfg.records_dir)
    if args.period and len(df):
        df = test_period(df, cfg, args.period)
        keep = set(df["target_day"])
        tab = tab[tab["target_day"].isin(keep)]
        base = base[base["target_day"].isin(keep)]
    if args.mode:
        modes = args.mode.split(",")
        df, tab, base = (x[x["mode"].isin(modes)] if len(x) else x for x in (df, tab, base))
    text = scorecard(cfg, df, tab, base, args.title)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(text)
    print(text)
    return 0


def cmd_compare(args) -> int:
    from .score import compare, load_frames, test_period
    cfg = load_config()
    a, _, _ = load_frames(Path(args.a).resolve() / "records")
    b, _, _ = load_frames(Path(args.b).resolve() / "records")
    a, b = test_period(a, cfg, args.period), test_period(b, cfg, args.period)
    groups = [(args.run, args.lead)] if args.run else [("evening", 1), ("early", 0), ("morning", 0), ("noon", 0), ("afternoon", 0)]
    out = {}
    for run, lead in groups:
        ga, gb = a[(a["run"] == run) & (a["lead"] == lead)], b[(b["run"] == run) & (b["lead"] == lead)]
        out[f"{run}_l{lead}"] = {metric: compare(ga, gb, cfg, metric) for metric in ("abs_error", "log_score")}
    print(json.dumps(out, indent=1))
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(out, indent=1))
    return 0


def cmd_reproduce(args) -> int:
    from .engine import build_ctx
    from .reproduce import reproduce_range
    cfg = _cfg(args)
    ctx = build_ctx(cfg, log=_log)
    n, diffs = reproduce_range(ctx, date.fromisoformat(args.start), date.fromisoformat(args.end), _log)
    for d in diffs[:20]:
        print(d)
    if args.out:
        Path(args.out).write_text(json.dumps({"start": args.start, "end": args.end, "files": n,
                                              "differences": len(diffs), "examples": diffs[:20]}, indent=1))
    return 1 if diffs else 0


def cmd_lookahead(args) -> int:
    import random
    from .lookahead import check
    cfg = _cfg(args)
    chain = cfg.data_dir
    rng = random.Random(args.seed)
    start, end = date.fromisoformat(args.start), date.fromisoformat(args.end)
    cutoffs = []
    for _ in range(args.n):
        d = start + timedelta(days=rng.randrange((end - start).days))
        kind = rng.choice(["slot", "slot+1s", "slot-1s", "random"])
        t = local_ts(d, rng.choice(["21:00", "06:00", "12:00", "01:00", "04:00"]))
        t += {"slot": 0, "slot+1s": 1, "slot-1s": -1, "random": rng.randrange(-3 * 3600, 3 * 3600)}[kind]
        cutoffs.append(t)
    for extra in args.include or []:
        cutoffs.append(to_ts(parse_iso(extra)))
    results = check(load_config(), chain, cutoffs, Path(args.work).resolve(), _log)
    out = Path(args.out) if args.out else None
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(results, indent=1))
    ok = all(r["unchanged_when_future_altered"] and r["changed_when_past_altered"] for r in results)
    _log("look-ahead test " + ("PASSED" if ok else "FAILED"))
    return 0 if ok else 1


def cmd_errortable(args) -> int:
    from .engine import build_ctx
    from .errortable import error_table, write_error_table
    from .score import load_frames
    cfg = _cfg(args)
    ctx = build_ctx(cfg, log=_log)
    _, _, base = load_frames(cfg.records_dir)
    rows = error_table(ctx, to_ts(datetime.now(UTC)), base)
    print(write_error_table(ctx, rows))
    return 0


def cmd_page(args) -> int:
    from .live import write_forecast_page
    print(write_forecast_page(load_config()))
    return 0


def cmd_checks(args) -> int:
    from .checks import write_checks, write_m3
    from .engine import build_ctx
    cfg = _cfg(args)
    write_checks(cfg, None, _log)
    if args.m3:
        write_m3(cfg, build_ctx(cfg, log=_log), _log)
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="smax", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("backfill", help="one-off history download (A4)")
    b.add_argument("--what", default="all", help="all or a comma list: knmi,iem,previous,publish,single")
    b.add_argument("--publish-from", default="2026-06-01")
    b.add_argument("--single-from", default=None)
    b.add_argument("--until", default=None)
    b.set_defaults(func=cmd_backfill)

    r = sub.add_parser("rebuild", help="ingest new raw files into the derived database")
    r.add_argument("--full", action="store_true", help="delete and recreate the database")
    r.set_defaults(func=cmd_rebuild)

    t = sub.add_parser("tick", help="the scheduled job: collect, then run everything that is due")
    t.add_argument("--now", default=None, help="pretend time (ISO with zone), for testing")
    t.add_argument("--dry-run", action="store_true", help="only list what is due")
    t.add_argument("--no-collect", action="store_true")
    t.set_defaults(func=cmd_tick)

    rp = sub.add_parser("replay", help="walk-forward backtest / extend the official record chain")
    rp.add_argument("--dir", default=None, help="write here instead of data/ (a backtest variant)")
    rp.add_argument("--variant", default="official")
    rp.add_argument("--set", action="append", help="config override, e.g. blend.method=mlpol")
    rp.add_argument("--start", default=None, help="first target day (default: live.chain_start)")
    rp.add_argument("--end", default=None, help="last moment (ISO, default now)")
    rp.add_argument("--runs", default=None)
    rp.set_defaults(func=cmd_replay)

    tg = sub.add_parser("target", help="Weather Underground values and target checks")
    tg.add_argument("action", choices=["set", "sheet", "check", "knmi"])
    tg.add_argument("day", nargs="?", help="YYYY-MM-DD (set), or the filled sheet path (check)")
    tg.add_argument("value", nargs="?", help="whole °C as shown on the WU history page")
    tg.add_argument("--confirm", action="store_true")
    tg.add_argument("--by", default="manual")
    tg.set_defaults(func=cmd_target)

    sub.add_parser("baselines", help="pass criterion 2 on the KNMI series").set_defaults(func=cmd_baselines)

    s = sub.add_parser("score", help="scorecard from records")
    s.add_argument("--dir", default=None)
    s.add_argument("--period", choices=["test", "tuning"], default=None)
    s.add_argument("--mode", default=None, help="replay, live, late (comma list)")
    s.add_argument("--title", default="Scorecard")
    s.add_argument("--out", default=None)
    s.set_defaults(func=cmd_score)

    c = sub.add_parser("compare", help="compare two backtest directories on the same days")
    c.add_argument("a")
    c.add_argument("b")
    c.add_argument("--run", default=None)
    c.add_argument("--lead", type=int, default=1)
    c.add_argument("--period", choices=["test", "tuning"], default="tuning")
    c.add_argument("--out", default=None)
    c.set_defaults(func=cmd_compare)

    rr = sub.add_parser("reproduce", help="criterion 9: re-run stored forecasts and compare")
    rr.add_argument("start")
    rr.add_argument("end")
    rr.add_argument("--dir", default=None)
    rr.add_argument("--out", default=None)
    rr.set_defaults(func=cmd_reproduce)

    la = sub.add_parser("lookahead", help="criterion 3: the automated look-ahead test")
    la.add_argument("--dir", default=None, help="record chain to test against (default: official)")
    la.add_argument("--n", type=int, default=6)
    la.add_argument("--seed", type=int, default=1)
    la.add_argument("--start", default="2025-10-15")
    la.add_argument("--end", default="2026-09-30")
    la.add_argument("--include", action="append", help="extra cut-off (ISO)")
    la.add_argument("--work", default="data/cache/lookahead")
    la.add_argument("--out", default=None)
    la.set_defaults(func=cmd_lookahead)

    e = sub.add_parser("errortable", help="C1–C3 error table and chart")
    e.add_argument("--dir", default=None)
    e.set_defaults(func=cmd_errortable)

    sub.add_parser("page", help="rewrite FORECAST.md").set_defaults(func=cmd_page)

    ck = sub.add_parser("checks", help="write the milestone check reports")
    ck.add_argument("--dir", default=None)
    ck.add_argument("--m3", action="store_true", help="also rebuild the error table (slower)")
    ck.set_defaults(func=cmd_checks)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
