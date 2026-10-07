"""Self-advancing milestones, so the build plan finishes without anyone signing off by hand.

A day counts as good when its completeness report shows no gap in our own collection (every expected fetch made,
every scheduled forecast run produced on time) and the nightly re-run of its forecasts matched exactly.

- M0 + M7: after 7 good days in a row, the same-day runs (06:00, 09:00, 12:00, 15:00) are switched on (M8) and the
  time since go-live is filled in by replay.
- M10: the soak starts the day after; after 60 good days in a row criterion 10 passes, the final report is written,
  and the pre-registered calibration decision is taken (below). A bad day restarts the count.

Pre-registered calibration decision (written 7 Oct 2026, before any live data):
the soak period is replayed with each refinement that was tried on the tuning year: Student-t (F5); spread level from
recent errors (F1 variant); both; MLpol (E3); spread from model disagreement (F6). Each is compared with the live
records on the same days (log score, whole-week bootstrap), for the day-ahead forecast (evening, lead 1). The variant
with the best mean is adopted only if its 95% interval excludes zero; otherwise nothing changes (PRD rule).

State: data/state/milestones.json (committed with the data).
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path

from .config import Config
from .timeutil import UTC, iso_z, local_date, local_ts, parse_ts

SAME_DAY_RUNS = ["early", "morning", "noon", "afternoon"]
STREAK_TO_SWITCH_ON = 7
SOAK_DAYS = 60
VARIANTS = {
    "f5_student_t": {"calibration.distribution": "student_t"},
    "f1_recent_spread": {"calibration.spread_method": "recent_season"},
    "f1_recent_spread_f5": {"calibration.spread_method": "recent_season", "calibration.distribution": "student_t"},
    "e3_mlpol": {"blend.method": "mlpol"},
    "f6_disagreement": {"calibration.disagreement_spread": True},
}


def path(cfg: Config) -> Path:
    return cfg.root / "data" / "state" / "milestones.json"


def load(cfg: Config) -> dict:
    p = path(cfg)
    state = json.loads(p.read_text()) if p.exists() else {}
    state.setdefault("days", {})
    state.setdefault("overrides", {})
    state.setdefault("events", [])
    for k in ("m0_m7_passed", "same_day_from", "soak_start", "soak_passed"):
        state.setdefault(k, None)
    state.setdefault("streak", 0)
    return state


def save(cfg: Config, state: dict) -> None:
    p = path(cfg)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state, indent=1, sort_keys=True) + "\n")


def effective_runs(cfg: Config, state: dict) -> list[str]:
    runs = list(cfg["live"]["runs"])
    if state.get("same_day_from"):
        runs += [r for r in SAME_DAY_RUNS if r not in runs]
    return runs


def apply_overrides(cfg: Config, state: dict) -> Config:
    return cfg.with_overrides(state["overrides"]) if state.get("overrides") else cfg


def note_day(state: dict, day: date, **fields) -> None:
    state["days"].setdefault(day.isoformat(), {}).update(fields)


def good(state: dict, day: date) -> bool:
    d = state["days"].get(day.isoformat(), {})
    return d.get("collection_problems") == 0 and d.get("reproduced") == "ok"


def streak(state: dict, last: date, first: date) -> int:
    n, d = 0, last
    while d >= first and good(state, d):
        n += 1
        d -= timedelta(days=1)
    return n


def first_live_day(cfg: Config) -> date:
    return local_date(parse_ts(cfg["live"]["go_live"])) + timedelta(days=1)


def advance(cfg: Config, state: dict, now: datetime, get_ctx, log) -> str:
    """Move milestones forward. Returns a one-line status for FORECAST.md."""
    today = local_date(int(now.timestamp()))
    last = today - timedelta(days=1)           # completeness and the re-run for `last` are done by 07:00 today

    if not state["same_day_from"]:
        n = streak(state, last, first_live_day(cfg))
        state["streak"] = n
        if n >= STREAK_TO_SWITCH_ON:
            switch_on_same_day(cfg, state, now, get_ctx, log)
        else:
            return f"Live since {cfg['live']['go_live'][:10]}: evening run on; same-day runs switch on after 7 clean days ({n}/7)."
    soak_first = local_date(parse_ts(state["same_day_from"])) + timedelta(days=1)
    if not state["soak_start"]:
        state["soak_start"] = soak_first.isoformat()
    if state["soak_passed"]:
        return f"All runs live. 60-day soak passed on {state['soak_passed']}; see reports/checks/M10.md."
    n = streak(state, last, soak_first)
    state["streak"] = n
    if n >= SOAK_DAYS:
        finish_soak(cfg, state, last - timedelta(days=SOAK_DAYS - 1), last, get_ctx, log)
        return f"All runs live. 60-day soak passed on {state['soak_passed']}; see reports/checks/M10.md."
    return f"All runs live since {state['same_day_from'][:10]}. 60-day soak: {n}/60 clean days in a row."


def switch_on_same_day(cfg: Config, state: dict, now: datetime, get_ctx, log) -> None:
    """M0 and M7 passed: switch on the same-day runs and fill the time since go-live by replay."""
    from .engine import replay

    ctx = get_ctx()
    start = parse_ts(cfg["live"]["go_live"])
    replay(ctx, start, int(now.timestamp()), SAME_DAY_RUNS)
    state["m0_m7_passed"] = (local_date(int(now.timestamp())) - timedelta(days=1)).isoformat()
    state["same_day_from"] = iso_z(int(now.timestamp()))
    state["events"].append({"at": iso_z(int(now.timestamp())), "event": "M0 and M7 passed (7 clean days in a row); "
                            "same-day runs switched on; gap since go-live filled by replay"})
    write_status_report(cfg, "M7.md", "M7 — Live day-ahead", "PASS",
                        f"7 days in a row ending {state['m0_m7_passed']} with every scheduled run on time, no collection gap, "
                        "and the nightly re-run identical to the stored records. The same-day runs were switched on "
                        f"at {state['same_day_from']} (M8).")
    write_status_report(cfg, "M0.md", "M0 — Collection running", "PASS",
                        f"7 clean completeness reports in a row ending {state['m0_m7_passed']} (`reports/completeness/`).")
    log(f"same-day runs switched on at {state['same_day_from']}")


def write_status_report(cfg: Config, name: str, title: str, status: str, text: str) -> None:
    p = cfg.reports_dir / "checks" / name
    old = p.read_text() if p.exists() else ""
    head = f"# {title}\n\n**Status: {status}** ({datetime.now(UTC):%Y-%m-%d %H:%M} UTC, automatic)\n\n{text}\n"
    body = old.split("\n", 1)[1] if old.startswith("# ") else old
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(head + "\n---\n" + body)


def finish_soak(cfg: Config, state: dict, first: date, last: date, get_ctx, log) -> None:
    """Criterion 10 passed: final scorecard, live-vs-backtest comparison and the pre-registered decision."""
    from .score import load_frames, metrics, scorecard

    df, tab, base = load_frames(cfg.records_dir)
    sel = lambda x: x[(x["target_day"] >= str(first)) & (x["target_day"] <= str(last)) & x["mode"].isin(["live", "late"])] if len(x) else x
    live, ltab, lbase = sel(df), sel(tab), sel(base)
    card = scorecard(cfg, live, ltab, lbase, f"Live soak scorecard: {first} to {last}")
    (cfg.reports_dir / "scorecards" / "live_soak.md").write_text(card)

    decision = calibration_decision(cfg, state, first, last, get_ctx, log)
    test = df[(df["mode"] == "replay") & (df["target_day"] >= "2025-10-01") & (df["target_day"] <= "2026-09-30")]
    rows = []
    for run, lead in [("evening", 1), ("early", 0), ("morning", 0), ("noon", 0), ("afternoon", 0)]:
        a = metrics(live[(live["run"] == run) & (live["lead"] == lead)])
        b = metrics(test[(test["run"] == run) & (test["lead"] == lead)])
        if a["n"]:
            rows.append(f"| {run} {lead} | {a['n']} | {a['hit_rate']:.1%} / {b.get('hit_rate', float('nan')):.1%} | "
                        f"{a['mae']:.2f} / {b.get('mae', float('nan')):.2f} | {a['coverage90']:.1%} / {b.get('coverage90', float('nan')):.1%} |")
    state["soak_passed"] = last.isoformat()
    state["events"].append({"at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                            "event": f"criterion 10 passed ({first} to {last}); {decision}"})
    text = "\n".join([
        f"60 days in a row ({first} to {last}) with every scheduled run produced on time, no collection gap and every "
        "nightly re-run identical. **Pass criterion 10: PASS.**", "",
        "Live (soak) against backtest (test year): hit rate, MAE °C and 90% coverage.", "",
        "| Run, lead | Live days | Hit rate live / backtest | MAE live / backtest | 90% coverage live / backtest |",
        "| --- | --- | --- | --- | --- |", *rows, "",
        f"Full live scorecard: `reports/scorecards/live_soak.md`.", "",
        f"Pre-registered calibration decision: {decision}",
    ])
    write_status_report(cfg, "M10.md", "M10 — Live soak", "PASS", text)
    with open(cfg.reports_dir / "decisions.md", "a") as fh:
        fh.write(f"\n## {datetime.now(UTC):%Y-%m-%d} — end of the live soak (automatic)\n\n{decision}\n")
    log(f"soak passed; {decision}")


def calibration_decision(cfg: Config, state: dict, first: date, last: date, get_ctx, log) -> str:
    """Replay the soak period with each refinement and adopt the best one only if it clearly wins."""
    from .engine import build_ctx, replay
    from .lookahead import _seed_store
    from .params import refit
    from .score import compare, load_frames

    work = cfg.root / "data" / "cache" / "soak_variants"
    start = local_ts(first - timedelta(days=1), "00:30")
    end = local_ts(last + timedelta(days=1), "00:59")
    data = get_ctx().data
    live, _, _ = load_frames(cfg.records_dir)
    live = live[(live["target_day"] >= str(first)) & (live["target_day"] <= str(last))]
    live = live[(live["run"] == "evening") & (live["lead"] == 1)]
    results = {}
    for name, overrides in VARIANTS.items():
        d = work / name
        _seed_store(cfg.data_dir, d, start)
        vcfg = cfg.with_overrides({**state.get("overrides", {}), **overrides}, data_dir=d)
        ctx = build_ctx(vcfg, data=data, last_day=last + timedelta(days=9), variant=name, log=lambda m: None)
        refit(ctx, start)                      # the variant's settings apply from the first day of the soak
        replay(ctx, start, end)
        v, _, _ = load_frames(d / "records")
        v = v[(v["target_day"] >= str(first)) & (v["target_day"] <= str(last))]
        v = v[(v["run"] == "evening") & (v["lead"] == 1)]
        results[name] = compare(live, v, cfg, "log_score")
        log(f"soak variant {name}: {results[name]}")
    (cfg.reports_dir / "soak_variants.json").write_text(json.dumps(results, indent=1))
    winners = {k: r for k, r in results.items() if r.get("n") and r["excludes_zero"] and r["mean_diff"] < 0}
    if not winners:
        return ("no refinement beat the live forecasts with an interval excluding zero; nothing changed "
                "(details: reports/soak_variants.json).")
    best = min(winners, key=lambda k: winners[k]["mean_diff"])
    state["overrides"] = {**state.get("overrides", {}), **VARIANTS[best]}
    state["refit_now"] = True
    r = winners[best]
    return (f"adopted {best} (log score {r['mean_diff']:+.4f}, 95% interval {r['ci_low']:+.4f} to {r['ci_high']:+.4f} "
            f"over {r['n']} days); it takes effect at the next refit (details: reports/soak_variants.json).")
