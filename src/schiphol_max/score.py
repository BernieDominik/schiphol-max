"""Metrics, calibration table, scorecards and version comparisons (testing section of the PRD).

Every figure comes from records and outcomes: either the walk-forward backtest or live running.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from .config import Config, load_config
from .timeutil import UTC


def load_frames(records_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """(forecasts joined with outcomes, listed table probabilities, baselines joined with outcomes)."""
    rows, table_rows, base_rows = [], [], []
    outcomes = {}
    odir = records_dir / "outcomes"
    if odir.exists():
        for p in odir.rglob("*.json"):
            o = json.loads(p.read_text())
            outcomes[(o["target_day"], o["run"], o["lead"])] = o
    fdir = records_dir / "forecasts"
    for p in sorted(fdir.rglob("*.json")) if fdir.exists() else []:
        f = json.loads(p.read_text())
        for r in f["records"]:
            o = outcomes.get((r["target_day"], r["run"], r["lead"]))
            if o is None:
                continue
            in_blend = [m for m in r["models"] if m["in_blend"]]
            row = {"target_day": pd.Timestamp(r["target_day"]), "run": r["run"], "lead": r["lead"],
                   "mode": f.get("mode", "replay"), "season": r["season"], "mu": r["mu"], "sigma": r["sigma"],
                   "top": r["top_degree"], "top_p": r["top_probability"], "outside": r["outside_table"],
                   "stated_five": 1 - r["outside_table"], "standard": r["standard_forecast"],
                   "degraded": r["degraded"], "n_models": len(in_blend), "target": o["target"],
                   "hit": o["hit"], "in_table": o["in_table"], "error": o["error"], "p_target": o["p_target"],
                   "log_score": o["log_score"], "pit": o["pit"], "standard_hit": o["standard_hit"],
                   "target_source": o["target_source"]}
            for m in r["models"]:
                row[f"raw:{m['name']}"] = m["raw"]
                row[f"cor:{m['name']}"] = m["corrected"]
            rows.append(row)
            for t in r["table"]:
                table_rows.append({"run": r["run"], "lead": r["lead"], "target_day": row["target_day"],
                                   "mode": row["mode"], "p": t["probability"], "is_target": t["degree"] == o["target"]})
            for b, bo in zip(f["baselines_by_day"].get(r["target_day"], []), o.get("baselines", [])):
                base_rows.append({"target_day": row["target_day"], "run": r["run"], "lead": r["lead"],
                                  "mode": row["mode"], "method": b["method"], "abs_error": abs(bo["error"]),
                                  "hit": bo["hit"], "log_score": bo["log_score"], "pit": bo["pit"]})
    df = pd.DataFrame(rows)
    if len(df):
        df = df.sort_values(["target_day", "run", "lead"]).reset_index(drop=True)
        df["abs_error"] = df["error"].abs()
        prev = df[df["run"] == "evening"].drop_duplicates("target_day").set_index("target_day")["target"]
        df["prev_target"] = df["target_day"].map(lambda d: prev.get(d - pd.Timedelta(days=1), np.nan))
    return df, pd.DataFrame(table_rows), pd.DataFrame(base_rows)


def metrics(df: pd.DataFrame) -> dict:
    if not len(df):
        return {"n": 0}
    return {"n": int(len(df)), "hit_rate": float(df["hit"].mean()), "mae": float(df["abs_error"].mean()),
            "log_score": float(df["log_score"].mean()),
            "coverage90": float(((df["pit"] >= 0.05) & (df["pit"] <= 0.95)).mean()),
            "five_coverage": float(df["in_table"].mean()), "stated_five": float(df["stated_five"].mean())}


BANDS = [(0.0, 0.10), (0.10, 0.20), (0.20, 0.30), (0.30, 0.40), (0.40, 0.50), (0.50, 1.01)]


def calibration_table(tab: pd.DataFrame) -> pd.DataFrame:
    """Criterion 6: every listed probability, banded; stated average against observed frequency."""
    out = []
    for lo, hi in BANDS:
        sel = tab[(tab["p"] >= lo) & (tab["p"] < hi)]
        out.append({"band": f"{lo:.0%}–{min(hi, 1):.0%}", "n": len(sel),
                    "stated": float(sel["p"].mean()) if len(sel) else np.nan,
                    "observed": float(sel["is_target"].mean()) if len(sel) else np.nan})
    t = pd.DataFrame(out)
    t["gap_pp"] = (t["observed"] - t["stated"]) * 100
    return t


def model_errors(df: pd.DataFrame, models: list[str]) -> pd.DataFrame:
    out = []
    for m in models:
        for kind in ("raw", "cor"):
            col = f"{kind}:{m}"
            if col in df:
                sel = df[[col, "target"]].dropna()
                if len(sel):
                    out.append({"model": m, "kind": "raw" if kind == "raw" else "corrected", "n": len(sel),
                                "mae": float((sel[col] - sel["target"]).abs().mean()),
                                "bias": float((sel[col] - sel["target"]).mean())})
    return pd.DataFrame(out)


def week_block_bootstrap(diff: pd.Series, days: pd.Series, n: int, seed: int) -> tuple[float, float, float]:
    """95% interval of a mean difference, resampling whole ISO weeks."""
    weeks = days.dt.strftime("%G-%V")
    groups = [g.values for _, g in diff.groupby(weeks.values)]
    rng = np.random.default_rng(seed)
    means = []
    for _ in range(n):
        pick = rng.integers(0, len(groups), len(groups))
        means.append(np.concatenate([groups[i] for i in pick]).mean())
    return float(diff.mean()), float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def compare(df_a: pd.DataFrame, df_b: pd.DataFrame, cfg: Config, metric: str = "abs_error") -> dict:
    """Difference B − A on the same (target day, run, lead) rows, with a whole-week bootstrap interval."""
    k = ["target_day", "run", "lead"]
    m = df_a[k + [metric]].merge(df_b[k + [metric]], on=k, suffixes=("_a", "_b"))
    if not len(m):
        return {"n": 0}
    diff = m[f"{metric}_b"] - m[f"{metric}_a"]
    mean, lo, hi = week_block_bootstrap(diff, m["target_day"], cfg["testing"]["bootstrap_resamples"],
                                        cfg["testing"]["bootstrap_seed"])
    return {"n": len(m), "mean_diff": mean, "ci_low": lo, "ci_high": hi, "excludes_zero": lo > 0 or hi < 0}


def fmt(v, pct=False, nd=2) -> str:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "–"
    return f"{v * 100:.1f}%" if pct else f"{v:.{nd}f}"


def metrics_table(groups: list[tuple[str, pd.DataFrame]]) -> list[str]:
    lines = ["| Group | n | Hit rate | MAE °C | Log score | 90% coverage | In five listed | Stated five |",
             "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for name, g in groups:
        m = metrics(g)
        if m["n"] == 0:
            continue
        lines.append(f"| {name} | {m['n']} | {fmt(m['hit_rate'], True)} | {fmt(m['mae'])} | {fmt(m['log_score'], nd=3)} | "
                     f"{fmt(m['coverage90'], True)} | {fmt(m['five_coverage'], True)} | {fmt(m['stated_five'], True)} |")
    return lines


def scorecard(cfg: Config, df: pd.DataFrame, tab: pd.DataFrame, base: pd.DataFrame, title: str) -> str:
    out = [f"# {title}", "", f"Generated {datetime.now(UTC):%Y-%m-%d %H:%M} UTC. Rows: forecasts with a known target.", ""]
    if not len(df):
        return "\n".join(out + ["No settled forecasts in this period."]) + "\n"
    out.append(f"Period: {df['target_day'].min():%Y-%m-%d} to {df['target_day'].max():%Y-%m-%d}.")
    out += ["", "## By run and lead", ""]
    groups = [(f"{r} lead {l}", g) for (r, l), g in df.groupby(["run", "lead"], sort=False)]
    order = {"evening": 0, "early": 1, "morning": 2, "noon": 3, "afternoon": 4}
    groups.sort(key=lambda x: (order.get(x[0].split()[0], 9), x[0]))
    out += metrics_table(groups)
    ev1 = df[(df["run"] == "evening") & (df["lead"] == 1)]
    out += ["", "## Evening run, lead 1, by season", ""]
    out += metrics_table([(s, g) for s, g in ev1.groupby("season")])
    out += ["", "## Difficult days (evening, lead 1)", ""]
    jump = ev1[(ev1["target"] - ev1["prev_target"]).abs() >= cfg["testing"]["jump_day_c"]]
    hot = ev1[ev1["target"] >= cfg["testing"]["hot_day_c"]]
    out += metrics_table([("all days", ev1), (f"moved ≥ {cfg['testing']['jump_day_c']} °C from previous day", jump),
                          (f"at or above {cfg['testing']['hot_day_c']} °C", hot)])
    out += ["", "## Calibration of every listed probability (all runs)", "",
            "| Stated band | n | Average stated | Observed | Gap (pp) |", "| --- | --- | --- | --- | --- |"]
    for _, r in calibration_table(tab).iterrows():
        out.append(f"| {r['band']} | {r['n']} | {fmt(r['stated'], True)} | {fmt(r['observed'], True)} | {fmt(r['gap_pp'], nd=1)} |")
    if len(base):
        out += ["", "## Baselines (MAE °C, hit rate)", "", "| Run, lead | Method | n | MAE | Hit rate | Log score |",
                "| --- | --- | --- | --- | --- | --- |"]
        for (r, l, mth), g in base.groupby(["run", "lead", "method"]):
            if r == "evening" or l == 0:
                out.append(f"| {r} {l} | {mth} | {len(g)} | {fmt(g['abs_error'].mean())} | {fmt(g['hit'].mean(), True)} | "
                           f"{fmt(g['log_score'].mean(), nd=3)} |")
    me = model_errors(ev1, cfg.collect_models)
    if len(me):
        out += ["", "## Weather models, evening lead 1 (same days)", "", "| Model | Kind | n | MAE | Bias |", "| --- | --- | --- | --- | --- |"]
        for _, r in me.iterrows():
            out.append(f"| {r['model']} | {r['kind']} | {r['n']} | {fmt(r['mae'])} | {fmt(r['bias'])} |")
    std_mae = (ev1["standard"] - ev1["target"]).abs().mean()
    out += ["", f"Standard forecast (evening lead 1): MAE {fmt(std_mae)} °C, hit rate {fmt(ev1['standard_hit'].mean(), True)}."]
    return "\n".join(out) + "\n"


def weekly_scorecard(cfg: Config, path: Path) -> str:
    df, tab, base = load_frames(cfg.records_dir)
    live = df[df["mode"].isin(["live", "late"])] if len(df) else df
    ltab = tab[tab["mode"].isin(["live", "late"])] if len(tab) else tab
    lbase = base[base["mode"].isin(["live", "late"])] if len(base) else base
    text = scorecard(cfg, live, ltab, lbase, "Weekly scorecard: live forecasts")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return str(path)


def period_bounds(cfg: Config, which: str = "test") -> tuple[pd.Timestamp, pd.Timestamp]:
    """The test year is the 12 months ending on `testing.test_end`; the tuning year is the 12 months before it.
    Every design choice is made on the tuning year; the test year is reported, never tuned on."""
    end = pd.Timestamp(cfg["testing"]["test_end"])
    months = cfg["testing"]["test_months"]
    start = end - pd.DateOffset(months=months) + pd.Timedelta(days=1)
    if which == "tuning":
        return start - pd.DateOffset(months=months), start - pd.Timedelta(days=1)
    return start, end


def test_period(df: pd.DataFrame, cfg: Config, which: str = "test") -> pd.DataFrame:
    if not len(df):
        return df
    start, end = period_bounds(cfg, which)
    return df[(df["target_day"] >= start) & (df["target_day"] <= end)]


__all__ = ["load_frames", "metrics", "calibration_table", "compare", "scorecard", "weekly_scorecard",
           "test_period", "load_config", "timedelta"]
