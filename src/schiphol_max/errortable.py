"""C1–C3: every weather model's error at Schiphol by lead and season, plus baselines and MOSMIX."""

from __future__ import annotations

import csv
from datetime import date

import numpy as np

from .engine import Ctx
from .schedule import issue_time
from .target import round_half_up
from .timeutil import season

SEASONS = ("all", "DJF", "MAM", "JJA", "SON")


def _row(name, lead, s, x, y) -> dict:
    err = x - y
    hits = np.array([round_half_up(v) for v in x]) == y
    return {"source": name, "lead": lead, "season": s, "days": int(len(x)), "bias": float(err.mean()),
            "mae": float(np.abs(err).mean()), "hit_rate": float(hits.mean())}


def error_table(ctx: Ctx, as_of: int, base_frame=None) -> list[dict]:
    pairs, data, cfg = ctx.pairs, ctx.data, ctx.cfg
    seasons = np.array([season(d) for d in pairs.days])
    rows = []
    for m in cfg.collect_models:
        for lead in range(1, 8):
            idx = pairs.known(m, ("evening", lead), as_of)
            if len(idx) == 0:
                continue
            x, y = pairs.series(m, ("evening", lead))["x"][idx], pairs.y[idx]
            for s in SEASONS:
                sel = slice(None) if s == "all" else seasons[idx] == s
                if np.sum(np.ones(len(idx))[sel]) >= 10:
                    rows.append(_row(m, lead, s, x[sel], y[sel]))
    # MOSMIX benchmark: only days since collection started (DWD keeps two days).
    for lead in range(1, 8):
        xs, ys, ss = [], [], []
        for i, d in enumerate(pairs.days):
            if np.isnan(pairs.y[i]) or pairs.y_avail[i] > as_of:
                continue
            v = data.mosmix_max(d, issue_time(cfg, "evening", lead, d))
            if v is not None:
                xs.append(v), ys.append(pairs.y[i]), ss.append(seasons[i])
        if len(xs) >= 1:
            rows.append(_row("mosmix", lead, "all", np.array(xs), np.array(ys)))
    if base_frame is not None and len(base_frame):
        ev = base_frame[base_frame["run"] == "evening"]
        for (method, lead), g in ev.groupby(["method", "lead"]):
            rows.append({"source": f"baseline:{method}", "lead": int(lead), "season": "all", "days": len(g),
                         "bias": float("nan"), "mae": float(g["abs_error"].mean()), "hit_rate": float(g["hit"].mean())})
    return rows


def write_error_table(ctx: Ctx, rows: list[dict]) -> tuple[str, str]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out = ctx.cfg.reports_dir
    out.mkdir(parents=True, exist_ok=True)
    csv_path = out / "error_table.csv"
    with open(csv_path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        for r in rows:
            w.writerow({k: (round(v, 3) if isinstance(v, float) else v) for k, v in r.items()})
    fig, ax = plt.subplots(figsize=(8, 5))
    for src in sorted({r["source"] for r in rows}):
        pts = sorted((r["lead"], r["mae"]) for r in rows if r["source"] == src and r["season"] == "all")
        if len(pts) >= 2:
            style = "--" if src.startswith("baseline") else "-"
            ax.plot([p[0] for p in pts], [p[1] for p in pts], style, marker="o", label=src)
    ax.set_xlabel("Lead (days; evening run)")
    ax.set_ylabel("MAE of raw daily maximum (°C)")
    ax.set_title("Schiphol daily maximum: error by lead")
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8, ncol=2)
    png = out / "error_table_mae_by_lead.png"
    fig.tight_layout()
    fig.savefig(png, dpi=120)
    plt.close(fig)
    return str(csv_path), str(png)


__all__ = ["error_table", "write_error_table", "date"]
