"""Milestone check reports (reports/checks/M<n>.md) and the pass-criteria summary.

Each report states the pass mark, the measured number, the command that produced it and the sample size.
The test year is the most recent 12 months with settled forecasts; tuning was done on the year before it.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from .access import Data
from .baselines import criterion2
from .config import Config
from .score import calibration_table, compare, load_frames, metrics, test_period
from .timeutil import UTC

V1_GROUPS = [("evening", 1), ("early", 0), ("morning", 0), ("noon", 0), ("afternoon", 0)]


def _pp(x) -> str:
    return "–" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x * 100:.1f}%"


def _f(x, nd=2) -> str:
    return "–" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x:.{nd}f}"


def _status(ok: bool | None) -> str:
    return {True: "PASS", False: "FAIL", None: "PENDING"}[ok]


def single_model_scores(df: pd.DataFrame, col: str, window: int = 365, min_n: int = 60) -> pd.DataFrame:
    """Criterion 4 needs a log score for each single corrected model and for the standard forecast.
    Each gets a normal spread equal to its own out-of-sample RMS error over the previous year."""
    s = df[["target_day", col, "target"]].dropna().sort_values("target_day").reset_index(drop=True)
    days = s["target_day"].values
    err = (s[col] - s["target"]).values
    out = []
    for i in range(len(s)):
        lo = np.searchsorted(days, days[i] - np.timedelta64(window, "D"))
        past = err[lo:i]
        if len(past) < min_n:
            continue
        sig = float(np.sqrt(np.mean(past ** 2)))
        c, y = s.at[i, col], s.at[i, "target"]
        p = stats.norm.cdf((y + 0.5 - c) / sig) - stats.norm.cdf((y - 0.5 - c) / sig)
        out.append({"target_day": s.at[i, "target_day"], "abs_error": abs(c - y), "log_score": -np.log(max(p, 1e-4))})
    return pd.DataFrame(out)


def criterion4(test: pd.DataFrame, full: pd.DataFrame) -> tuple[bool, list[str]]:
    """Blend against every corrected model and the standard forecast, on the same test-year days."""
    def ev1(x: pd.DataFrame) -> pd.DataFrame:
        x = x[(x["run"] == "evening") & (x["lead"] == 1)].copy()
        x["std_center"] = x[[c for c in x.columns if c.startswith("raw:")]].mean(axis=1)
        return x

    ev, full_ev = ev1(test), ev1(full)
    rows = ["| Compared with | Days | MAE: blend vs other | Log score: blend vs other | Blend better on both |",
            "| --- | --- | --- | --- | --- |"]
    ok = True
    for col in [c for c in ev.columns if c.startswith("cor:")] + ["std_center"]:
        name = "standard forecast" if col == "std_center" else col[4:] + " (corrected)"
        sc = single_model_scores(full_ev, col)
        sc = sc[sc["target_day"].isin(ev["target_day"])] if len(sc) else sc
        if len(sc) < 60:
            rows.append(f"| {name} | {len(sc)} | – | – | too few days to judge |")
            continue
        m = ev.merge(sc, on="target_day", suffixes=("", "_o"))
        better = bool(m["abs_error"].mean() < m["abs_error_o"].mean() and m["log_score"].mean() < m["log_score_o"].mean())
        ok &= better
        rows.append(f"| {name} | {len(m)} | {_f(m['abs_error'].mean())} vs {_f(m['abs_error_o'].mean())} | "
                    f"{_f(m['log_score'].mean(), 3)} vs {_f(m['log_score_o'].mean(), 3)} | {'yes' if better else 'NO'} |")
    return ok, rows


def write_checks(cfg: Config, only: list[str] | None = None, log=print) -> None:
    out = cfg.reports_dir / "checks"
    out.mkdir(parents=True, exist_ok=True)
    data = Data(cfg)
    df, tab, base = load_frames(cfg.records_dir)
    replay_df = df[df["mode"] == "replay"]
    test = test_period(replay_df, cfg, "test")
    t0, t1 = test["target_day"].min(), test["target_day"].max()
    tab_t = tab[(tab["mode"] == "replay") & tab["target_day"].between(t0, t1)]
    base_t = base[(base["mode"] == "replay") & base["target_day"].between(t0, t1)]
    stamp = f"Generated {datetime.now(UTC):%Y-%m-%d %H:%M} UTC from the official record chain (`data/records`)."
    period = f"Test year: {t0:%Y-%m-%d} to {t1:%Y-%m-%d} (walk-forward backtest; nothing fitted on a day it forecasts)."
    status: dict[int, tuple[bool | None, str]] = {}

    # ---------------- criterion 1
    sheet = cfg.reports_dir / "wu_check_sheet.csv"
    from .target import check_sheet, target_vs_knmi
    c1 = check_sheet(cfg, data, sheet) if sheet.exists() else {"filled": 0, "agree": 0, "pass": False, "mismatches": []}
    c1_ok = None if c1["filled"] < 60 else c1["pass"]
    status[1] = (c1_ok, f"{c1['agree']} of {c1['filled']} sample days agree" if c1["filled"] else
                 "open: needs a person to read 60 WU pages (WU forbids automated reading); the system uses the airport-report maximum meanwhile")
    (out / "M1.md").write_text("\n".join([
        "# M1 — Target series", "", stamp, "",
        f"**Pass criterion 1 (rebuilt target matches the Weather Underground page on ≥ 57 of 60 sample days): {_status(c1_ok)}**", "",
        f"Sample sheet: `reports/wu_check_sheet.csv` (15 days per season, 12 with the maximum before 09:00 or after 20:00). "
        f"Filled: {c1['filled']} of 60; agree: {c1['agree']}.",
        "Fill the `wu_max_c` column from the WU page (units °C), then run `uv run smax target check reports/wu_check_sheet.csv`. "
        "The sheet is blind; the rebuilt values are in `reports/wu_check_key.csv`.", "",
        "Since 7 Oct 2026 the live target is the airport-report maximum itself, settled automatically, because nobody "
        "enters WU values by hand. This check would confirm that it equals the WU page.",
        "", "Mismatches: " + (", ".join(f"{d} rebuilt {r} vs WU {w} (max at {t})" for d, r, w, t in c1["mismatches"]) or "none"), "",
        "## Rebuilt target against the KNMI official maximum (rounded half up), by month", "",
        "The KNMI series covers 00–24 UTC and is a continuous maximum in tenths; the target is the highest half-hourly "
        "airport report of the Amsterdam day, so it is usually equal or 1 °C lower.", "",
        target_vs_knmi(cfg, data), "",
        f"Target history: genuine half-hourly reports from {cfg['target']['history_from']} ({len(data.rebuilt)} days). "
        "IEM labels the :25 reports 'specials', so both report types are used; rows rebuilt by IEM from synoptic data are excluded.",
    ]) + "\n")

    # ---------------- criterion 2
    c2 = criterion2(data)
    targets = {"persistence": 2.00, "climatology": 2.68, "autoregression": 1.88}
    c2_ok = all(abs(c2[k] - v) <= 0.10 for k, v in targets.items())
    status[2] = (c2_ok, ", ".join(f"{k} {c2[k]:.2f}" for k in targets))
    (out / "M2.md").write_text("\n".join([
        "# M2 — Baselines", "", stamp, "",
        f"**Pass criterion 2 (baselines reproduce the research figures within 0.10 °C): {_status(c2_ok)}**", "",
        "KNMI official maximum, station 240; fit 1971–2015, test 2016–2025, lead 1. Command: `uv run smax baselines`.", "",
        "| Baseline | Research MAE | Measured MAE | Difference |", "| --- | --- | --- | --- |",
        *[f"| {k} | {v:.2f} | {c2[k]:.3f} | {c2[k] - v:+.3f} |" for k, v in targets.items()], "",
        f"Fitted autoregression coefficient: {c2['ar_coefficient']} (research: about 0.74). Test days: {c2['n_test_days']}.",
    ]) + "\n")

    # ---------------- criterion 3
    la_path = cfg.reports_dir / "lookahead.json"
    la = json.loads(la_path.read_text()) if la_path.exists() else []
    c3_ok = (all(r["unchanged_when_future_altered"] and r["changed_when_past_altered"] for r in la) if la else None)
    status[3] = (c3_ok, f"{len(la)} cut-offs" if la else "not run")
    ev1 = test[(test["run"] == "evening") & (test["lead"] == 1)]
    corr_rows = []
    for lead in range(1, 8):
        g = test[(test["run"] == "evening") & (test["lead"] == lead)]
        for m in cfg.collect_models:
            rc, cc = f"raw:{m}", f"cor:{m}"
            if rc in g and cc in g:
                s = g[[rc, cc, "target"]].dropna()
                if len(s) >= 30:
                    raw_mae = (s[rc] - s["target"]).abs().mean()
                    cor_mae = (s[cc] - s["target"]).abs().mean()
                    corr_rows.append(f"| {m} | {lead} | {len(s)} | {raw_mae:.3f} | {cor_mae:.3f} | {'yes' if cor_mae < raw_mae else 'NO'} |")
    (out / "M4.md").write_text("\n".join([
        "# M4 — Corrections and test harness", "", stamp, "", period, "",
        f"**Pass criterion 3 (no look-ahead: altering data dated after an issue time leaves that forecast unchanged): {_status(c3_ok)}**", "",
        "Command: `uv run smax lookahead`. At each cut-off the chain is replayed three times: with real data; with every value "
        "published after the cut-off altered, deleted or invented (including an airport report observed before the cut-off "
        "but received after it); and, as a control, with data published before the cut-off altered. Every forecast, outcome "
        "and parameter set up to the cut-off must be byte-identical in the first two, and must differ in the control.", "",
        "| Cut-off (UTC) | Outputs compared | Unchanged when future altered | Changed when past altered (control) |",
        "| --- | --- | --- | --- |",
        *[f"| {r['cutoff']} | {r['outputs_compared']} | {r['unchanged_when_future_altered']} | {r['changed_when_past_altered']} |" for r in la],
        "", "## Each corrected model against its own raw forecast (test year, evening run)", "",
        "| Model | Lead | Days | Raw MAE | Corrected MAE | Corrected better |", "| --- | --- | --- | --- | --- | --- |",
        *corr_rows,
    ]) + "\n")

    # ---------------- criteria 4, 5
    c4_ok, c4_rows = criterion4(test, replay_df)
    ar = base_t[(base_t["run"] == "evening") & (base_t["lead"] == 1) & (base_t["method"] == "autoregression")]
    m_ev1 = metrics(ev1)
    ar_mae = float(ar["abs_error"].mean()) if len(ar) else np.nan
    c5_ok = bool(m_ev1["mae"] <= 0.75 * ar_mae)
    status[4] = (c4_ok, f"blend MAE {m_ev1['mae']:.2f}, log score {m_ev1['log_score']:.3f}")
    status[5] = (c5_ok, f"blend MAE {m_ev1['mae']:.2f} vs autoregression {ar_mae:.2f} ({1 - m_ev1['mae'] / ar_mae:.0%} lower)")
    (out / "M5.md").write_text("\n".join([
        "# M5 — Blend", "", stamp, "", period, "",
        f"**Pass criterion 4 (day-ahead blend has lower MAE and lower log score than every single corrected model and the "
        f"standard forecast): {_status(c4_ok)}**", "",
        "Same days only. Single models and the standard forecast get a normal spread equal to their own out-of-sample RMS "
        "error over the previous year, so their log scores are comparable.", "", *c4_rows, "",
        f"**Pass criterion 5 (day-ahead blend MAE at least 25% below the autoregression baseline): {_status(c5_ok)}**", "",
        f"Evening run, lead 1: blend MAE {m_ev1['mae']:.3f} °C over {m_ev1['n']} days; autoregression {ar_mae:.3f} °C "
        f"({1 - m_ev1['mae'] / ar_mae:.1%} lower).",
    ]) + "\n")

    # ---------------- criteria 6, 7, 9, 11
    groups = {"day-ahead (evening, lead 1)": (tab_t[(tab_t["run"] == "evening") & (tab_t["lead"] == 1)], ev1),
              "same-day (all four runs)": (tab_t[tab_t["lead"] == 0], test[test["lead"] == 0])}
    lines6, c6_ok, c7_ok, c11_ok = [], True, True, True
    lines7, lines11 = [], []
    for name, (tb, g) in groups.items():
        ct = calibration_table(tb)
        lines6 += [f"### {name}", "", "| Stated band | n | Average stated | Observed | Gap (pp) | Counts (n ≥ 100) | Within 5 pp |",
                   "| --- | --- | --- | --- | --- | --- | --- |"]
        for _, r in ct.iterrows():
            counts = r["n"] >= 100
            within = abs(r["gap_pp"]) <= 5 if counts else None
            if counts and not within:
                c6_ok = False
            lines6.append(f"| {r['band']} | {r['n']} | {_pp(r['stated'])} | {_pp(r['observed'])} | {_f(r['gap_pp'], 1)} | "
                          f"{'yes' if counts else 'no'} | {'' if within is None else ('yes' if within else 'NO')} |")
        lines6.append("")
        m = metrics(g)
        cov_ok = 0.86 <= m["coverage90"] <= 0.94
        seas = []
        for s, gs in g.groupby("season"):
            ms = metrics(gs)
            sok = 0.84 <= ms["coverage90"] <= 0.96
            cov_ok &= sok
            seas.append(f"{s} {_pp(ms['coverage90'])} (n {ms['n']})")
        c7_ok &= cov_ok
        lines7.append(f"| {name} | {_pp(m['coverage90'])} | {', '.join(seas)} | {'yes' if cov_ok else 'NO'} |")
        gap = abs(m["five_coverage"] - m["stated_five"])
        c11_ok &= gap <= 0.04
        lines11.append(f"| {name} | {m['n']} | {_pp(m['five_coverage'])} | {_pp(m['stated_five'])} | {gap * 100:.1f} | "
                       f"{'yes' if gap <= 0.04 else 'NO'} |")
    rep_path = cfg.reports_dir / "reproduce.json"
    rep = json.loads(rep_path.read_text()) if rep_path.exists() else None
    c9_ok = None if rep is None else rep["differences"] == 0
    status[6] = (c6_ok, "every band with n ≥ 100 within 5 pp" if c6_ok else "a band is off by more than 5 pp")
    status[7] = (c7_ok, "; ".join(l.split("|")[2].strip() for l in lines7))
    status[9] = (c9_ok, f"{rep['files']} files re-run, {rep['differences']} differences" if rep else "not run")
    status[11] = (c11_ok, "; ".join(f"{l.split('|')[3].strip()} vs {l.split('|')[4].strip()}" for l in lines11))
    (out / "M6.md").write_text("\n".join([
        "# M6 — Probabilities and output", "", stamp, "", period, "",
        f"**Pass criterion 6 (in every band with ≥ 100 listed probabilities, observed frequency within 5 pp of the stated average): {_status(c6_ok)}**", "",
        "Every probability in the five-degree table counts, not only the top one.", "", *lines6,
        f"**Pass criterion 7 (90% interval coverage 86–94% overall, 84–96% in each season): {_status(c7_ok)}**", "",
        "| Group | Overall | By season | Pass |", "| --- | --- | --- | --- |", *lines7, "",
        f"**Pass criterion 9 (re-running stored forecasts from raw data and stored parameters gives identical records): {_status(c9_ok)}**", "",
        (f"Command: `uv run smax reproduce {rep['start']} {rep['end']}`: {rep['files']} forecast files re-run, {rep['differences']} differences."
         if rep else "Not run yet."), "",
        f"**Pass criterion 11 (share of days inside the five-degree table within 4 pp of the average stated total): {_status(c11_ok)}**", "",
        "| Group | Days | Target inside table | Average stated total | Gap (pp) | Pass |", "| --- | --- | --- | --- | --- | --- |",
        *lines11,
    ]) + "\n")

    # ---------------- criterion 8
    rows8 = []
    for run in ("early", "morning", "noon", "afternoon"):
        g = test[(test["run"] == run)]
        m = metrics(g)
        if m["n"]:
            ct = calibration_table(tab_t[tab_t["run"] == run])
            worst = ct[ct["n"] >= 100]["gap_pp"].abs().max()
            rows8.append(f"| {run} | {m['n']} | {_pp(m['hit_rate'])} | {_f(m['mae'])} | {_f(m['log_score'], 3)} | "
                         f"{_pp(m['coverage90'])} | {_f(worst, 1)} | {g['n_models'].mean():.1f} |")
    c8_ok = len(rows8) == 4
    status[8] = (c8_ok, "measured for all four issue hours" if c8_ok else "missing runs")
    (out / "M8.md").write_text("\n".join([
        "# M8 — Same-day runs", "", stamp, "", period, "",
        f"**Pass criterion 8 (hit rate, MAE and calibration reported for each of the four issue hours, with sample sizes): {_status(c8_ok)}**", "",
        "| Run | Days | Hit rate | MAE °C | Log score | 90% coverage | Worst calibration gap (pp, bands n ≥ 100) | Models in blend |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |", *rows8, "",
        "Caveat: exact runs exist for the European model from March 2024 but for the other models only from April 2026, "
        "so through most of the test year the same-day blend is the European model alone (flagged degraded). The other "
        "models join as they reach 180 days of same-day history.",
    ]) + "\n")

    # ---------------- criterion 10 and the live checks
    status[10] = (None, "60-day live soak not started")
    summary = ["# Pass criteria for version 1", "", stamp, "", period, "",
               "| # | Criterion | Status | Measured |", "| --- | --- | --- | --- |"]
    names = {1: "Rebuilt target matches the WU page", 2: "Baselines reproduce the research figures", 3: "No look-ahead",
             4: "Day-ahead blend beats its inputs", 5: "Day-ahead blend beats the baselines", 6: "Probabilities are honest",
             7: "Spread is honest", 8: "Same-day runs are measured", 9: "Past forecasts can be reproduced",
             10: "It runs unattended (60 days)", 11: "The five-degree table is honest"}
    for i in range(1, 12):
        ok, txt = status.get(i, (None, ""))
        summary.append(f"| {i} | {names[i]} | {_status(ok)} | {txt} |")
    summary += ["", "Milestone reports: [M1](M1.md) · [M2](M2.md) · [M4](M4.md) · [M5](M5.md) · [M6](M6.md) · [M8](M8.md). "
                "M0, M3, M7, M9 and M10 are written separately ([M0](M0.md), [M3](M3.md), [M7](M7.md), [M9](M9.md), [M10](M10.md))."]
    (out / "README.md").write_text("\n".join(summary) + "\n")
    log(f"wrote check reports to {out}")
    for i in range(1, 12):
        log(f"criterion {i}: {_status(status.get(i, (None, ''))[0])} — {status.get(i, (None, ''))[1]}")


__all__ = ["write_checks", "compare", "Path", "date", "timedelta"]


def write_m3(cfg: Config, ctx, log=print) -> None:
    """M3: the error table (C1–C3, all history) and a keep/drop recommendation per model judged on data
    before the test year only."""
    from .errortable import error_table, write_error_table
    from .score import period_bounds
    from .timeutil import local_ts

    _, _, base = load_frames(cfg.records_dir)
    now = int(datetime.now(UTC).timestamp())
    rows = error_table(ctx, now, base)
    csv_path, png = write_error_table(ctx, rows)
    test_start = period_bounds(cfg, "test")[0].date()
    pre = error_table(ctx, local_ts(test_start, "00:00"), None)
    lead1 = {r["source"]: r for r in pre if r["lead"] == 1 and r["season"] == "all"}
    best = min((r["mae"] for r in lead1.values()), default=np.nan)
    lines = ["# M3 — Error table", "", f"Generated {datetime.now(UTC):%Y-%m-%d %H:%M} UTC.", "",
             f"Deliverables: `{Path(csv_path).name}` (every model, lead 1–7, by season, plus baselines and MOSMIX) and "
             f"`{Path(png).name}`. Bias is forecast minus target; hit rate is the rounded raw forecast equal to the target.", "",
             "## Raw error at lead 1 (evening run), all seasons", "",
             "| Source | Days | Bias °C | MAE °C | Hit rate |", "| --- | --- | --- | --- | --- |"]
    for r in sorted((r for r in rows if r["lead"] == 1 and r["season"] == "all"), key=lambda r: r["mae"]):
        lines.append(f"| {r['source']} | {r['days']} | {_f(r['bias'])} | {_f(r['mae'])} | {_pp(r['hit_rate'])} |")
    lines += ["", f"## Which models stay in: recommendation (judged on history before the test year, i.e. before {test_start})", "",
              "| Model | Lead-1 days | Raw MAE | Recommendation |", "| --- | --- | --- | --- |"]
    for m in cfg.collect_models:
        r = lead1.get(m)
        if r is None:
            rec = ("keep — no honest lead-1 history before April 2026 (the day-ahead archive cannot be replayed without "
                   "look-ahead for this short-range model); it joins the blend after 180 days and its weight is earned live")
            lines.append(f"| {m} | 0 | – | {rec} |")
            continue
        if r["days"] < 180:
            rec = "keep — short history; joins the blend only after 180 days (D4)"
        elif r["mae"] <= 1.5 * best:
            rec = "keep"
        else:
            rec = "keep in collection, review weight — raw error well above the best model; correction may rescue it"
        lines.append(f"| {m} | {r['days']} | {_f(r['mae'])} | {rec} |")
    biased = [r for r in rows if r["lead"] == 1 and r["season"] == "all" and not r["source"].startswith(("baseline", "mosmix"))
              and abs(r["bias"]) >= 1.0]
    if biased:
        lines += ["", "Systematic biases at lead 1 (raw forecast minus target), removed by each model's correction: " +
                  "; ".join(f"{r['source']} {r['bias']:+.2f} °C" for r in biased) + ". HARMONIE runs about 2.4 °C warm in "
                  "spring and summer and 1 °C warm in autumn at the Schiphol grid point, steadily from day to day, so it "
                  "is a model property rather than a data error."]
    lines += ["", "Dropping a model from the blend never stops it being collected (separate `collect` and `blend` "
              "flags in `config.yaml`). Inverse-MAE weighting (E1) already gives weak models little weight.", "",
              "**Decision needed from the product owner:** confirm the list above (default: keep all eight)."]
    (cfg.reports_dir / "checks" / "M3.md").write_text("\n".join(lines) + "\n")
    log("wrote M3")
