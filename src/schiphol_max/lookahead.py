"""Pass criterion 3, automated: altering any data dated after an issue time leaves that forecast unchanged.

For each cut-off: copy the record chain up to a start point, replay to the cut-off twice — once with the real
data and once with every value that became available after the cut-off changed, deleted or invented — and
require every forecast, outcome and parameter set up to the cut-off to be byte-identical. A control run that
changes data available *before* the cut-off must produce a difference, proving the test can see one.
"""

from __future__ import annotations

import copy
import json
import shutil
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path

import numpy as np

from .access import Data, Run
from .config import Config
from .engine import build_ctx, replay
from .learn import Pairs
from .engine import first_data_day
from .timeutil import HOUR, from_ts, local_date, local_ts


def perturb(data: Data, cutoff: int, rng: np.random.Generator, before: bool = False) -> Data:
    """Copy of `data` with everything available after `cutoff` altered (or, with before=True, the
    last three days *before* the cut-off altered, as a control)."""
    d = copy.deepcopy(data)
    lo, hi = (cutoff - 3 * 86400, cutoff) if before else (cutoff, np.iinfo(np.int64).max)

    def hit(avail) -> bool:
        return lo < avail <= hi

    for m, ms in d.models.items():
        kept = []
        for run in ms.runs:
            if hit(run.available):
                if rng.random() < 0.15:
                    continue                                      # delete
                run = replace(run, temp=run.temp + rng.normal(0, 3, len(run.temp)))
            kept.append(run)
        if kept and not before:                                   # invent a run published after the cut-off
            src = kept[-1]
            fake_t = (cutoff // (3 * HOUR) + 1) * 3 * HOUR
            kept.append(Run(m, fake_t, cutoff + 600, src.valid + (fake_t - src.run), src.temp + 5.0))
        kept.sort(key=lambda r: r.run)
        ms.runs, ms.run_times = kept, [r.run for r in kept]
        if ms.prev_valid is not None:
            for i in np.nonzero(ms.prev_valid >= cutoff - 9 * 86400)[0]:
                t = int(ms.prev_valid[i])
                for n in range(1, 8):
                    if hit(d.run_available(m, d.prev_source_run(m, t, n))):
                        ms.prev_temp[i, n] += rng.normal(0, 3)
    # Airport reports: alter, delete, and invent reports published after the cut-off (one observed before it).
    mask = (d.report_avail > lo) & (d.report_avail <= hi)
    temp = d.report_temp.copy()
    temp[mask] += rng.integers(-4, 5, mask.sum())
    keep = ~(mask & (rng.random(len(mask)) < 0.2))
    obs, temp, avail = d.report_obs[keep], temp[keep], d.report_avail[keep]
    if not before:
        extra_obs = np.array([cutoff - 600, cutoff + 900], dtype=np.int64)
        extra_avail = np.array([cutoff + 60, cutoff + 1200], dtype=np.int64)
        obs = np.concatenate([obs, extra_obs])
        temp = np.concatenate([temp, [45.0, 45.0]])
        avail = np.concatenate([avail, extra_avail])
        order = np.argsort(obs, kind="stable")
        obs, temp, avail = obs[order], temp[order], avail[order]
    d.report_obs, d.report_temp, d.report_avail = obs, temp, avail
    for day, (v, a, n) in list(d.rebuilt.items()):
        if hit(a):
            d.rebuilt[day] = (v + int(rng.integers(1, 4)), a, n)
    for day, (v, a) in list(d.wu.items()):
        if hit(a):
            d.wu[day] = (v - 2, a)
    return d


def _seed_store(src_dir: Path, dst_dir: Path, start: int) -> None:
    """Copy records issued before `start`, their outcomes settled before it, and params effective before it."""
    if dst_dir.exists():
        shutil.rmtree(dst_dir)
    for p in (src_dir / "records" / "forecasts").rglob("*.json"):
        f = json.loads(p.read_text())
        if _ts(f["issued_at_utc"]) < start:
            q = dst_dir / p.relative_to(src_dir)
            q.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(p, q)
    for p in (src_dir / "records" / "outcomes").rglob("*.json"):
        o = json.loads(p.read_text())
        if _ts(o["settled_at_utc"]) < start:
            q = dst_dir / p.relative_to(src_dir)
            q.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(p, q)
    for p in (src_dir / "params").rglob("params_*.json"):
        if _ts(json.loads(p.read_text())["effective_from_utc"]) < start:
            q = dst_dir / p.relative_to(src_dir)
            q.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(p, q)


def _ts(s: str) -> int:
    from .timeutil import parse_ts
    return parse_ts(s)


def _snapshot(base: Path, cutoff: int) -> dict[str, str]:
    """Every output up to the cut-off, minus the wall-clock fields that legitimately differ between runs."""
    out = {}
    for p in sorted(base.rglob("*.json")):
        obj = json.loads(p.read_text())
        if "records" in obj:
            if _ts(obj["issued_at_utc"]) > cutoff:
                continue
            obj.pop("produced_at_utc", None)
        elif "settled_at_utc" in obj:
            if _ts(obj["settled_at_utc"]) > cutoff:
                continue
        elif "effective_from_utc" in obj:
            if _ts(obj["effective_from_utc"]) > cutoff:
                continue
            obj.pop("fitted_at_utc", None)
        out[str(p.relative_to(base))] = json.dumps(obj, sort_keys=True)
    return out


def check(cfg: Config, chain_dir: Path, cutoffs: list[int], work: Path, log=print) -> list[dict]:
    """Run the test at each cut-off. `chain_dir` holds an existing record chain (the official one or a dev replay)."""
    data = Data(cfg)
    results = []
    rng = np.random.default_rng(3)
    for cutoff in cutoffs:
        start = local_ts(local_date(cutoff) - timedelta(days=9), "00:30")
        row = {"cutoff": from_ts(cutoff).isoformat()}
        snaps = {}
        for label, d in (("real", data), ("after", perturb(data, cutoff, rng)), ("before", perturb(data, cutoff, rng, before=True))):
            run_dir = work / label
            _seed_store(chain_dir, run_dir, start)
            c = cfg.with_overrides({}, data_dir=run_dir)
            ctx = build_ctx(c, data=d, last_day=local_date(cutoff) + timedelta(days=9), variant=cfg.raw.get("variant", "official"),
                            log=lambda m: None)
            replay(ctx, start, cutoff)
            snaps[label] = _snapshot(run_dir, cutoff)
        same_after = snaps["real"] == snaps["after"]
        differs_before = snaps["real"] != snaps["before"]
        row.update({"outputs_compared": len(snaps["real"]), "unchanged_when_future_altered": same_after,
                    "changed_when_past_altered": differs_before})
        if not same_after:
            row["differing"] = [k for k in snaps["real"] if snaps["real"].get(k) != snaps["after"].get(k)][:5]
        results.append(row)
        log(str(row))
    return results


__all__ = ["check", "perturb", "Pairs", "first_data_day", "date"]
