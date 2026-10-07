"""Weekly refit (D2, I2): corrections, spreads, same-day shifts and baselines, saved with the moment they take effect (I4).

Everything is fitted from data and outcomes known at the refit time, so a late refit gives the same result.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import numpy as np

from .baselines import fit_baselines
from .calibrate import fit_t_df
from .correct import fit_correction, predict
from .schedule import keys
from .store import content_hash
from .timeutil import UTC, iso_z, local_date, season

SEASONS = ("DJF", "MAM", "JJA", "SON")
MIN_FIT_DAYS = 30


def keystr(key: tuple[str, int]) -> str:
    return f"{key[0]}_l{key[1]}"


def record_errors(ctx, key, as_of: int, window_days: int, *, skip_degraded: bool = True):
    """Out-of-sample blend errors (mu − target) of records for `key` whose target was known at `as_of`."""
    pairs, store = ctx.pairs, ctx.store
    k = store.records(key)
    first = local_date(as_of).toordinal() - window_days
    out = []
    for i in store.window(key, first, local_date(as_of).toordinal() + 1):
        rec = k["rec"][i]
        if skip_degraded and rec.get("degraded"):
            continue
        j = pairs.index_of(date.fromordinal(k["ord"][i]))
        if j < 0 or j >= len(pairs.y) or pairs.y_avail[j] > as_of:
            continue
        out.append((rec, float(pairs.y[j])))
    return out


def _sigma_table(ctx, key, R: int) -> dict:
    cal = ctx.cfg["calibration"]
    # Day-ahead: skip records from before three models were in the blend. Same-day: the blend is structurally
    # thin until the other models' exact runs reach 180 days (2026), so its own errors are used throughout (G4).
    skip = key[1] >= 1
    if cal.get("spread_method", "season") == "recent_season":
        table = _recent_season_sigma(ctx, key, R, skip)
        if table is not None:
            return table
    errs = record_errors(ctx, key, R, cal["window_days"], skip_degraded=skip)
    by_season = {s: [] for s in SEASONS}
    for rec, y in errs:
        by_season[season(date.fromisoformat(rec["target_day"]))].append(rec["mu"] - y)
    pooled = [e for v in by_season.values() for e in v]
    if len(pooled) >= cal["min_errors"]:
        fallback, source = float(np.sqrt(np.mean(np.square(pooled)))), "pooled"
    else:
        fallback, source = _anchor_sigma(ctx, key, R), "anchor"
    table = {}
    for s, v in by_season.items():
        if len(v) >= cal["min_errors"]:
            table[s] = {"sigma": float(np.sqrt(np.mean(np.square(v)))), "n": len(v), "source": "season"}
        else:
            table[s] = {"sigma": fallback, "n": len(pooled), "source": source}
    return table


def _recent_season_sigma(ctx, key, R: int, skip: bool) -> dict | None:
    """F1 variant: the level of the spread from the most recent errors, its seasonal shape from two years.

    Seasonal factor f(s) = RMS of season-s errors / RMS of all errors over the last two years. The level is the RMS
    of the last `recent_days` errors, each divided by its own season's factor; the spread for season s is that level
    times f(s). This follows improvements in the blend within weeks instead of a year later."""
    cal = ctx.cfg["calibration"]
    long = record_errors(ctx, key, R, 730, skip_degraded=skip)
    if len(long) < 2 * cal["min_errors"]:
        return None
    err = np.array([rec["mu"] - y for rec, y in long])
    seas = np.array([season(date.fromisoformat(rec["target_day"])) for rec, _ in long])
    days = np.array([date.fromisoformat(rec["target_day"]).toordinal() for rec, _ in long])
    overall = float(np.sqrt(np.mean(err ** 2)))
    factor = {}
    for s in SEASONS:
        sel = seas == s
        factor[s] = float(np.sqrt(np.mean(err[sel] ** 2)) / overall) if sel.sum() >= cal["min_errors"] else 1.0
    recent = days >= local_date(R).toordinal() - cal["recent_days"]
    if recent.sum() < cal["min_errors"]:
        return None
    norm = err[recent] / np.array([factor[s] for s in seas[recent]])
    level = float(np.sqrt(np.mean(norm ** 2)))
    return {s: {"sigma": level * factor[s], "n": int(recent.sum()), "source": "recent_season"} for s in SEASONS}


def _anchor_sigma(ctx, key, R: int) -> float:
    """Before blend errors exist: the anchor model's own in-sample correction error (wider, so safe)."""
    cfg, pairs = ctx.cfg, ctx.pairs
    m = cfg["anchor_model"]
    idx = pairs.known(m, key, R)
    if len(idx) >= MIN_FIT_DAYS:
        x = pairs.series(m, key)["x"][idx]
        p = fit_correction(x, pairs.y[idx], pairs.doy[idx], cfg["correction"]["ridge_alpha"],
                           cfg["correction"]["seasonal_after_days"])
        res = pairs.y[idx] - predict(p, x, pairs.doy[idx])
        return float(np.sqrt(np.mean(res[-365:] ** 2)))
    return float(cfg["calibration"]["fallback_sigma"].get(key[1], 2.0))


def refit(ctx, R: int) -> dict:
    cfg, pairs = ctx.cfg, ctx.pairs
    corr = cfg["correction"]
    out = {"effective_from_utc": iso_z(R), "fitted_at_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "code_version": ctx.code_version, "variant": ctx.variant, "corrections": {}, "sigma": {},
           "sameday": {}, "baselines": {}, "t_df": None, "disagreement": {}}

    # D1/D2: one correction per model and key, on all history known at R.
    for m in cfg.collect_models:
        for key in keys(cfg):
            idx = pairs.known(m, key, R)
            if len(idx) < MIN_FIT_DAYS:
                continue
            x = pairs.series(m, key)["x"][idx]
            p = fit_correction(x, pairs.y[idx], pairs.doy[idx], corr["ridge_alpha"], corr["seasonal_after_days"])
            out["corrections"].setdefault(m, {})[keystr(key)] = {k: (round(v, 6) if isinstance(v, float) else v)
                                                                 for k, v in p.items()}

    # F1 and G4: spread per key and season from out-of-sample blend errors.
    for key in keys(cfg):
        out["sigma"][keystr(key)] = _sigma_table(ctx, key, R)

    # G3: same-day shift per issue hour.
    from .sameday import fit_shift
    for key in keys(cfg):
        if key[1] != 0:
            continue
        rows = [(y - rec["mu_before_shift"], rec["error_so_far"])
                for rec, y in record_errors(ctx, key, R, 100000, skip_degraded=False)
                if rec.get("error_so_far") is not None]
        res = np.array([r[0] for r in rows]) if rows else np.zeros(0)
        err = np.array([r[1] for r in rows]) if rows else np.zeros(0)
        out["sameday"][key[0]] = fit_shift(res, err, cfg["sameday"]["min_records"])

    # B1–B3 on the whole target history known at R.
    days, vals = [], []
    for d in sorted(set(ctx.data.rebuilt) | set(ctx.data.wu)):
        t = ctx.data.target(d, R)
        if t is not None:
            days.append(d)
            vals.append(t[0])
    if len(days) > 730:
        b = fit_baselines(days, np.array(vals, dtype=float))
        out["baselines"] = b

    # F5 variant: tail weight from standardised past errors, pooled over keys.
    cal = cfg["calibration"]
    if cal["distribution"] == "student_t":
        out["t_df_by_run"] = {}
        for run in {k[0] for k in keys(cfg)}:
            z = [(y - rec["mu"]) / rec["sigma"] for key in keys(cfg) if key[0] == run
                 for rec, y in record_errors(ctx, key, R, cal["window_days"], skip_degraded=key[1] >= 1)]
            out["t_df_by_run"][run] = fit_t_df(np.array(z)) if len(z) >= 200 else (cal.get("t_df") or 30.0)

    # F6 variant: spread scaled by how much the models disagree, in thirds of past disagreement.
    if cal["disagreement_spread"]:
        for key in keys(cfg):
            rows = [(rec["model_disagreement"], rec["mu"] - y) for rec, y in record_errors(ctx, key, R, cal["window_days"])
                    if rec.get("model_disagreement") is not None]
            if len(rows) < 3 * cal["min_errors"]:
                continue
            dis = np.array([r[0] for r in rows])
            err = np.array([r[1] for r in rows])
            edges = [float(np.quantile(dis, 1 / 3)), float(np.quantile(dis, 2 / 3))]
            overall = float(np.sqrt(np.mean(err ** 2)))
            factors = []
            for lo, hi in ((-np.inf, edges[0]), (edges[0], edges[1]), (edges[1], np.inf)):
                sel = (dis > lo) & (dis <= hi)
                factors.append(float(np.sqrt(np.mean(err[sel] ** 2)) / overall) if sel.any() else 1.0)
            out["disagreement"][keystr(key)] = {"edges": edges, "factors": factors}

    out["hash"] = content_hash({k: v for k, v in out.items() if k not in ("fitted_at_utc",)})
    ctx.params.save(out)
    return out


__all__ = ["refit", "keystr", "record_errors", "SEASONS", "timedelta"]
