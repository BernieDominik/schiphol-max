"""The forecast function, settling and the slot loop. Live running and backtests call exactly this code.

forecast_slot() runs pipeline steps 2–6 for one scheduled run (PRD "How the system works");
settle() is step 7's scoring; refit() (params.py) and the running bias (learn.py) are its learning.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

import numpy as np

from . import calibrate
from .access import Data
from .baselines import METHODS, baseline_forecasts
from .blend import blend, inverse_mae_weights, mlpol_weights
from .config import Config, code_version
from .correct import predict
from .deviation import against_standard, standard_forecast
from .learn import Pairs, corrected_history, running_bias
from .params import keystr, refit
from .record import summary_text
from .sameday import blended_error, model_error_so_far
from .schedule import slots_between, target_days
from .store import ParamStore, RecordStore
from .timeutil import UTC, iso_z, local_date, parse_ts, season, to_ts


@dataclass
class Ctx:
    cfg: Config
    data: Data
    pairs: Pairs
    store: RecordStore
    params: ParamStore
    code_version: str
    variant: str = "official"
    log: object = print
    stats: dict = field(default_factory=dict)


def first_data_day(cfg: Config) -> date:
    return min(date.fromisoformat(m.previous_runs_from) for m in cfg.models.values())


def build_ctx(cfg: Config, *, data: Data | None = None, last_day: date | None = None,
              variant: str = "official", log=print) -> Ctx:
    data = data or Data(cfg)
    last_day = last_day or (datetime.now(UTC).date() + timedelta(days=9))
    pairs = Pairs(cfg, data, first_data_day(cfg), last_day)
    return Ctx(cfg, data, pairs, RecordStore(cfg), ParamStore(cfg), code_version(cfg.root), variant, log)


def _r(x: float | None, nd: int) -> float | None:
    return None if x is None else round(float(x), nd)


# ---------------------------------------------------------------- weights

def model_maes(ctx: Ctx, key, issue: int, models: list[str], P: dict) -> dict[str, float]:
    """E1: MAE of each model's corrected forecast as issued, over the last 60 days with a known target.
    Until a model has enough issued records, its corrections are replayed on the same days instead."""
    cfg, pairs, store = ctx.cfg, ctx.pairs, ctx.store
    window = cfg["blend"]["mae_window_days"]
    today = local_date(issue).toordinal()
    k = store.records(key)
    errs: dict[str, list[float]] = {m: [] for m in models}
    for i in store.window(key, today - window, today + 1):
        j = pairs.index_of(date.fromordinal(k["ord"][i]))
        if pairs.y_avail[j] > issue:
            continue
        y = pairs.y[j]
        for e in k["rec"][i]["models"]:
            if e["name"] in errs and e["corrected"] is not None:
                errs[e["name"]].append(abs(e["corrected"] - y))
    out = {}
    for m in models:
        if len(errs[m]) >= cfg["blend"]["min_mae_days"]:
            out[m] = float(np.mean(errs[m]))
            continue
        pc = P["corrections"].get(m, {}).get(keystr(key))
        idx = pairs.known(m, key, issue)
        idx = idx[pairs.day_ord[idx] >= today - window]
        if pc is None or len(idx) == 0:
            continue
        x = pairs.series(m, key)["x"][idx]
        out[m] = float(np.mean(np.abs(pairs.y[idx] - predict(pc, x, pairs.doy[idx]))))
    return out


def mlpol_history(ctx: Ctx, key, issue: int, models: list[str]) -> list[tuple[dict, float]]:
    pairs, store = ctx.pairs, ctx.store
    k = store.records(key)
    hist = []
    for i, rec in enumerate(k["rec"]):
        j = pairs.index_of(date.fromordinal(k["ord"][i]))
        if k["issue"][i] >= issue or pairs.y_avail[j] > issue:
            continue
        fc = {e["name"]: e["corrected"] for e in rec["models"] if e["name"] in models and e["corrected"] is not None}
        hist.append((fc, float(pairs.y[j])))
    return hist


# ---------------------------------------------------------------- one target day

BASE_SETTINGS = {"blend_method": "inverse_mae", "distribution": "normal", "disagreement_spread": False}


def forecast_day(ctx: Ctx, run: str, lead: int, day: date, issue: int, P: dict) -> tuple[dict, list] | None:
    cfg, data, pairs = ctx.cfg, ctx.data, ctx.pairs
    settings = {**BASE_SETTINGS, **(P.get("settings") or {})}
    key = (run, lead)
    ks = keystr(key)
    doy = day.timetuple().tm_yday
    j = pairs.index_of(day)
    min_days = cfg["correction"]["min_paired_days"]
    mso = data.max_so_far(day, issue) if lead == 0 else None

    entries, corrected, eligible, raws = [], {}, [], {}
    for m in cfg.collect_models:
        rf = pairs.get_raw(m, key, day)
        if rf is None:
            continue
        raws[m] = rf
        pc = P["corrections"].get(m, {}).get(ks)
        c = r = None
        if pc is not None:
            idx, res = corrected_history(pairs, m, key, pc, issue)
            r = running_bias(res, pairs.bias_weight(m)[idx])
            c = float(predict(pc, rf.value, doy)) + r
            corrected[m] = c
            if cfg.models[m].blend and len(idx) >= min_days:
                eligible.append(m)
        entries.append({"name": m, "run_time_utc": iso_z(rf.run) if rf.run is not None else None,
                        "raw": _r(rf.value, 2), "corrected": _r(c, 2), "weight": 0.0, "stale": rf.stale,
                        "in_blend": False, "source": rf.source, "running_bias": _r(r, 3)})
    if not corrected:
        return None

    degraded = len(eligible) < cfg["blend"]["min_models"]
    pool = eligible or list(corrected)            # with no eligible model, fall back to every corrected model
    if settings["blend_method"] == "mlpol" and eligible:
        weights = mlpol_weights(mlpol_history(ctx, key, issue, pool), pool)
    else:
        maes = model_maes(ctx, key, issue, pool, P)
        missing = [m for m in pool if m not in maes]
        if missing and maes:
            worst = max(maes.values())
            maes.update({m: worst for m in missing})
        weights = inverse_mae_weights(maes) if maes else {m: 1 / len(pool) for m in pool}
    weights = {m: w for m, w in weights.items() if m in corrected}
    tot = sum(weights.values()) or 1.0
    weights = {m: w / tot for m, w in weights.items()}
    mu = blend(corrected, weights)
    for e in entries:
        if e["name"] in weights:
            e["weight"] = _r(weights[e["name"]], 4)
            e["in_blend"] = True

    mu_before_shift, err = mu, None
    if lead == 0:
        errs = {m: model_error_so_far(data, raws[m].run_obj, corrected[m] - raws[m].value, issue,
                                      cfg["sameday"]["error_window_hours"]) for m in weights}
        err = blended_error(errs, weights)
        shift = P["sameday"].get(run, {"a": 0.0, "k": 0.0})
        mu = mu + shift["a"] + (shift["k"] * err if err is not None else 0.0)

    cal = cfg["calibration"]
    srow = P["sigma"][ks][season(day)]
    sigma = srow["sigma"]
    disagreement = float(np.std([corrected[m] for m in weights])) if len(weights) > 1 else 0.0
    dis = P.get("disagreement", {}).get(ks)
    if settings["disagreement_spread"] and dis:
        third = 0 if disagreement <= dis["edges"][0] else (1 if disagreement <= dis["edges"][1] else 2)
        sigma *= dis["factors"][third]
    dist = settings["distribution"]
    df = (P.get("t_df_by_run") or {}).get(run, P.get("t_df")) if dist == "student_t" else None
    if dist == "student_t" and not df:
        dist = "normal"                     # tail weight not fitted yet: stay normal until the next refit
    probs = calibrate.degree_probabilities(mu, sigma, cal, dist=dist, df=df, max_so_far=mso)
    top = calibrate.top_degree(probs, mu)
    table, outside = calibrate.five_degree_table(probs, top, cal["decimals"])

    std = standard_forecast([rf.value for rf in raws.values()])
    dev = against_standard(probs, std, cfg["deviation"]["miss_threshold_c"])
    prev_mu = ctx.store.previous_mu(day, issue)
    rec = {
        "target_day": day.isoformat(), "run": run, "lead": lead, "issued_at_utc": iso_z(issue),
        "top_degree": top, "top_probability": probs[top], "table": table, "outside_table": outside,
        "probabilities": {str(k): v for k, v in sorted(probs.items())},
        "mu": _r(mu, 2), "sigma": _r(sigma, 3), "distribution": dist if dist == "normal" else f"student_t({df:g})",
        "standard_forecast": std, **dev,
        "p_miss_2_or_more_typical": ctx.store.typical_p_miss(key, issue, cfg["deviation"]["typical_window_days"]),
        "max_so_far": mso, "model_disagreement": _r(disagreement, 3),
        "models": entries, "degraded": degraded,
        "parameter_version": P["effective_from_utc"], "parameter_hash": P["hash"], "code_version": ctx.code_version,
        "season": season(day), "mu_change": _r(mu - prev_mu, 2) if prev_mu is not None else None,
        "mu_before_shift": _r(mu_before_shift, 3) if lead == 0 else None,
        "error_so_far": _r(err, 3) if lead == 0 else None,
        "spread_source": srow["source"],
    }

    base = []
    bf = baseline_forecasts(P.get("baselines") or {}, data, day, issue)
    for method in METHODS if bf else ():
        bmu, bsig = bf[method]
        bp = calibrate.degree_probabilities(bmu, bsig, cal, max_so_far=mso)
        base.append({"method": method, "mu": _r(bmu, 2), "sigma": _r(bsig, 3), "top_degree": calibrate.top_degree(bp, bmu),
                     "probabilities": {str(k): v for k, v in sorted(bp.items())}})
    return rec, base


# ---------------------------------------------------------------- slots

def forecast_slot(ctx: Ctx, run: str, issue: int, produced_at: int | None = None, mode: str = "replay") -> bool:
    if ctx.store.has_forecast(run, issue):
        return False
    P = ctx.params.at(issue)
    if P is None:
        P = refit(ctx, issue)
    records, baselines = [], {}
    for lead, day in target_days(ctx.cfg, run, local_date(issue)):
        out = forecast_day(ctx, run, lead, day, issue, P)
        if out is None:
            ctx.log(f"no forecast possible: {run} lead {lead} for {day}")
            continue
        rec, base = out
        records.append(rec)
        baselines[rec["target_day"]] = base
    produced_at = produced_at or to_ts(datetime.now(UTC))
    if mode == "live" and produced_at - issue > ctx.cfg["schedule"]["on_time_minutes"] * 60:
        mode = "late"
    payload = {"run": run, "issue_day": local_date(issue).isoformat(), "issued_at_utc": iso_z(issue),
               "produced_at_utc": iso_z(produced_at), "mode": mode, "variant": ctx.variant,
               "code_version": ctx.code_version, "parameter_version": P["effective_from_utc"],
               "records": records, "baselines_by_day": baselines,
               "summary": "\n\n".join(summary_text(r) for r in records[:2])}
    return ctx.store.write_forecast(run, issue, payload)


def settle(ctx: Ctx, as_of: int, stamp: int | None = None) -> int:
    """Score every forecast whose target is known by `as_of` (I1). One write-once outcome per forecast record."""
    n = 0
    for key, day, rec, base in sorted(ctx.store.unsettled(), key=lambda x: (x[1], x[0])):
        t = ctx.data.target(day, as_of)
        if t is None:
            continue
        y, src, avail = t
        probs = {int(k): v for k, v in rec["probabilities"].items()}
        p = probs.get(y, 0.0)
        table = [row["degree"] for row in rec["table"]]
        bl = []
        for b in base:
            bprobs = {int(k): v for k, v in b["probabilities"].items()}
            bp = bprobs.get(y, 0.0)
            bl.append({"method": b["method"], "error": _r(b["mu"] - y, 3), "hit": b["top_degree"] == y,
                       "p_target": bp, "log_score": _r(-math.log(max(bp, 1e-4)), 4),
                       "pit": _r(calibrate.mid_pit(bprobs, y), 4)})
        outcome = {"target_day": day.isoformat(), "run": key[0], "lead": key[1], "issued_at_utc": rec["issued_at_utc"],
                   "target": y, "target_source": src, "target_available_utc": iso_z(avail),
                   "settled_at_utc": iso_z(stamp if stamp is not None else as_of),
                   "hit": rec["top_degree"] == y, "in_table": y in table, "error": _r(rec["mu"] - y, 3),
                   "p_target": p, "log_score": _r(-math.log(max(p, 1e-4)), 4),
                   "pit": _r(calibrate.mid_pit(probs, y), 4), "standard_hit": rec["standard_forecast"] == y,
                   "baselines": bl}
        if ctx.store.write_outcome(key, day, outcome):
            n += 1
    return n


def replay(ctx: Ctx, start: int, end: int, runs: list[str] | None = None, progress_every: int = 30) -> None:
    """Walk-forward backtest: the scheduled slots in time order, each using only what was known then."""
    slots = slots_between(ctx.cfg, start, end, runs)
    if not slots:
        return
    if ctx.params.at(slots[0].ts) is None:
        refit(ctx, slots[0].ts - 1)
    last_day = None
    for s in slots:
        if s.kind == "settle":
            settle(ctx, s.ts, stamp=s.ts)
        elif s.kind == "refit" and not ctx.params.has(s.ts):
            refit(ctx, s.ts)
        elif s.kind == "forecast":
            forecast_slot(ctx, s.run, s.ts, mode="replay")
        if s.day != last_day and s.day.day == 1 and s.kind == "settle":
            ctx.log(f"replayed to {s.day}")
        last_day = s.day


__all__ = ["Ctx", "build_ctx", "forecast_slot", "settle", "replay", "parse_ts"]
