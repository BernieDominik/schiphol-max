"""Open-Meteo collectors: exact model runs (Single Runs), the day-ahead archive (Previous Runs),
run publish times (open-data bucket) and the ensemble.

Everything is requested in UTC (`timezone=GMT`, unix times): Open-Meteo applies one fixed offset
to a whole requested range, so asking for Europe/Amsterdam would shift winter days by an hour.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from ..config import Config
from ..net import FetchError, Http
from ..rawstore import raw_path, write_raw
from ..timeutil import UTC, from_ts, iso_z, parse_ts, to_ts

SINGLE_URL = "https://single-runs-api.open-meteo.com/v1/forecast"
PREVIOUS_URL = "https://previous-runs-api.open-meteo.com/v1/forecast"
ENSEMBLE_URL = "https://ensemble-api.open-meteo.com/v1/ensemble"
BUCKET = "https://openmeteo.s3.amazonaws.com"


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _base_params(cfg: Config) -> dict:
    loc = cfg["location"]
    return {"latitude": loc["latitude"], "longitude": loc["longitude"],
            "timezone": "GMT", "timeformat": "unixtime"}


# ---------------------------------------------------------------- Single Runs

def run_name(run_ts: int) -> str:
    return from_ts(run_ts).strftime("%Y%m%dT%H%MZ")


def single_run_path(cfg: Config, model: str, run_ts: int):
    return raw_path(cfg, f"single_runs/{model}", from_ts(run_ts).date(), run_name(run_ts))


def have_single_run(cfg: Config, model: str, run_ts: int, include_unavailable: bool = True) -> bool:
    p = single_run_path(cfg, model, run_ts)
    if p.exists():
        return True
    return include_unavailable and p.with_name(p.name.replace(".json.gz", ".unavailable.json.gz")).exists()


def fetch_single_runs(cfg: Config, http: Http, run_ts: int, models: list[str]) -> dict[str, str]:
    """Fetch one run time for several models in one call; fall back to one call per model.
    Writes one raw file per model and run. Returns {model: 'ok'|'unavailable'|'exists'}."""
    todo = [m for m in models if not have_single_run(cfg, m, run_ts)]
    result = {m: "exists" for m in models if m not in todo}
    if not todo:
        return result
    params = _base_params(cfg) | {
        "hourly": "temperature_2m",
        "run": from_ts(run_ts).strftime("%Y-%m-%dT%H:%M"),
        "forecast_days": cfg["collection"]["forecast_days"],
    }
    specs = cfg.models

    def store(model: str, body: dict | None, status: int, url: str, error: str | None = None) -> None:
        payload = {"source": "single_runs", "model": model, "openmeteo": specs[model].openmeteo,
                   "run": iso_z(run_ts), "fetched_at": _now_iso(), "url": url, "status": status,
                   "error": error, "body": body}
        name = run_name(run_ts) if body is not None else run_name(run_ts) + ".unavailable"
        write_raw(cfg, f"single_runs/{model}", from_ts(run_ts).date(), name, payload)

    if len(todo) > 1:
        ids = ",".join(specs[m].openmeteo for m in todo)
        try:
            r = http.get(SINGLE_URL, params | {"models": ids}, openmeteo=True)
        except FetchError:
            r = None
        if r is not None:
            body = r.json()
            hourly = body.get("hourly", {})
            for m in todo:
                key = f"temperature_2m_{specs[m].openmeteo}"
                one = {"hourly": {"time": hourly.get("time", []), "temperature_2m": hourly.get(key)},
                       "latitude": body.get("latitude"), "longitude": body.get("longitude")}
                store(m, one, r.status, r.url)
                result[m] = "ok"
            return result
    for m in todo:
        try:
            r = http.get(SINGLE_URL, params | {"models": specs[m].openmeteo}, openmeteo=True,
                         ok_statuses=(200, 400))
        except FetchError as exc:
            result[m] = f"failed: {exc}"
            continue
        if r.status == 400:
            reason = r.json().get("reason", r.text[:200])
            # An unavailable run is a fact about the source: record it so completeness can tell.
            if "not available" in reason:
                store(m, None, r.status, r.url, reason)
                result[m] = "unavailable"
            else:
                result[m] = f"failed: {reason}"
            continue
        body = r.json()
        store(m, {"hourly": body.get("hourly", {}), "latitude": body.get("latitude"),
                  "longitude": body.get("longitude")}, r.status, r.url)
        result[m] = "ok"
    return result


def scheduled_runs(cfg: Config, model: str, start_ts: int, end_ts: int) -> list[int]:
    """Run start times of `model` in [start, end] that the Single Runs archive keeps."""
    spec = cfg.models[model]
    first = max(start_ts, parse_ts(spec.single_runs_from))
    out = []
    t = first - first % 3600
    while t <= end_ts:
        if from_ts(t).hour in spec.run_hours and t >= first:
            out.append(t)
        t += 3600
    return out


def backfill_single_runs(cfg: Config, http: Http, start_ts: int, end_ts: int, log=print) -> None:
    """Fetch every archived run in [start, end] that is not stored yet, grouping models per run time."""
    by_time: dict[int, list[str]] = {}
    for m in cfg.collect_models:
        for t in scheduled_runs(cfg, m, start_ts, end_ts):
            if not have_single_run(cfg, m, t):
                by_time.setdefault(t, []).append(m)
    log(f"single runs to fetch: {sum(len(v) for v in by_time.values())} model-runs in {len(by_time)} calls")
    for i, t in enumerate(sorted(by_time)):
        res = fetch_single_runs(cfg, http, t, by_time[t])
        bad = {m: s for m, s in res.items() if s not in ("ok", "exists")}
        if bad or i % 200 == 0:
            log(f"  {iso_z(t)} {res if bad else 'ok'} ({i + 1}/{len(by_time)})")


# ---------------------------------------------------------------- Latest run and publish times

def latest_run_info(cfg: Config, http: Http, model: str) -> dict:
    """Newest run held by the Single Runs archive, with the time the bucket says it was written."""
    spec = cfg.models[model]
    r = http.get(f"{BUCKET}/data_run/{spec.publish_dir}/latest.json")
    body = r.json()
    return {"model": model, "reference_time": body.get("reference_time"), "created_at": body.get("created_at"),
            "last_modified": r.headers.get("Last-Modified")}


def record_latest_runs(cfg: Config, http: Http, now: datetime) -> dict[str, int]:
    """Save every model's newest archived run and when the bucket says it was written. Returns {model: run}."""
    items, latest = [], {}
    for model in cfg.collect_models:
        try:
            info = latest_run_info(cfg, http, model)
        except FetchError as exc:
            info = {"model": model, "error": str(exc)}
        items.append(info)
        if info.get("reference_time"):
            latest[model] = parse_ts(info["reference_time"])
    write_raw(cfg, "latest_runs", now.date(), f"latest_{now:%Y%m%dT%H%M}",
              {"source": "latest_runs", "fetched_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "models": items})
    return latest


def catch_up_single_runs(cfg: Config, http: Http, now: datetime, latest: dict[str, int], days: int = 3) -> dict:
    """Live collection: every archived run of the last `days` days up to each model's newest run."""
    start = to_ts(now) - days * 86400
    by_time: dict[int, list[str]] = {}
    for m in cfg.collect_models:
        if m not in latest:
            continue
        for t in scheduled_runs(cfg, m, start, latest[m]):
            if not have_single_run(cfg, m, t):
                by_time.setdefault(t, []).append(m)
    results = {}
    for t in sorted(by_time):
        results[iso_z(t)] = fetch_single_runs(cfg, http, t, by_time[t])
    return results


def _list_keys(http: Http, prefix: str) -> list[tuple[str, str]]:
    keys, token = [], None
    while True:
        params = {"list-type": "2", "prefix": prefix}
        if token:
            params["continuation-token"] = token
        x = http.get(BUCKET + "/", params).text
        keys += re.findall(r"<Key>([^<]+)</Key><LastModified>([^<]+)</LastModified>", x)
        m = re.search(r"<NextContinuationToken>([^<]+)</NextContinuationToken>", x)
        if not m:
            return keys
        token = m.group(1)


def collect_publish_times(cfg: Config, http: Http, day: date) -> None:
    """Record when each run of each model was written to Open-Meteo's open-data bucket on `day`.
    One raw file per model and day; re-listing the same day later is skipped once stored."""
    for model in cfg.collect_models:
        spec = cfg.models[model]
        path = raw_path(cfg, f"publish_times/{model}", day, f"{day:%Y%m%d}")
        if path.exists():
            continue
        prefix = f"data_run/{spec.publish_dir}/{day:%Y/%m/%d}/"
        keys = _list_keys(http, prefix)
        runs = {}
        for key, modified in keys:
            m = re.match(rf"{re.escape(prefix)}(\d{{4}})Z/meta\.json$", key)
            if m:
                hhmm = m.group(1)
                run = datetime(day.year, day.month, day.day, int(hhmm[:2]), int(hhmm[2:]), tzinfo=UTC)
                runs[iso_z(to_ts(run))] = modified
        if not runs and day >= (datetime.now(UTC) - timedelta(days=1)).date():
            continue  # the day is not finished yet; list it again later
        write_raw(cfg, f"publish_times/{model}", day, f"{day:%Y%m%d}",
                  {"source": "publish_times", "model": model, "prefix": prefix, "fetched_at": _now_iso(),
                   "runs": runs})


# ---------------------------------------------------------------- Previous Runs

def fetch_previous_runs(cfg: Config, http: Http, model: str, start: date, end: date) -> None:
    """Day-ahead archive for one model and date range (days 0..7 before valid time)."""
    spec = cfg.models[model]
    name = f"{start:%Y%m%d}_{end:%Y%m%d}"
    if raw_path(cfg, f"previous_runs/{model}", start, name).exists():
        return
    variables = ["temperature_2m"] + [f"temperature_2m_previous_day{n}" for n in range(1, 8)]
    days = (end - start).days + 1
    weight = max(1.0, len(variables) / 10 * max(1.0, days / 14))
    params = _base_params(cfg) | {"hourly": ",".join(variables), "models": spec.openmeteo,
                                  "start_date": start.isoformat(), "end_date": end.isoformat()}
    r = http.get(PREVIOUS_URL, params, openmeteo=True, weight=weight, timeout=180)
    body = r.json()
    write_raw(cfg, f"previous_runs/{model}", start, name,
              {"source": "previous_runs", "model": model, "openmeteo": spec.openmeteo, "fetched_at": _now_iso(),
               "url": r.url, "status": r.status, "body": {"hourly": body.get("hourly", {})}})


def backfill_previous_runs(cfg: Config, http: Http, end: date, log=print, chunk_days: int = 90) -> None:
    """Whole history in fixed 90-day chunks counted from each model's archive start."""
    for model in cfg.collect_models:
        start = date.fromisoformat(cfg.models[model].previous_runs_from)
        s = start
        while s <= end:
            e = min(s + timedelta(days=chunk_days - 1), end)
            fetch_previous_runs(cfg, http, model, s, e)
            s += timedelta(days=chunk_days)
        log(f"previous runs: {model} {start} → {end} stored")


# ---------------------------------------------------------------- Ensemble (kept for later add-ons)

def collect_ensemble(cfg: Config, http: Http, day: date) -> None:
    for ens in cfg["ensembles"]:
        name = f"{ens['name']}_{day:%Y%m%d}"
        if raw_path(cfg, "ensemble", day, name).exists():
            continue
        params = _base_params(cfg) | {"hourly": "temperature_2m", "models": ens["openmeteo"],
                                      "forecast_days": cfg["collection"]["forecast_days"]}
        r = http.get(ENSEMBLE_URL, params, openmeteo=True, weight=6)
        write_raw(cfg, "ensemble", day, name, {"source": "ensemble", "model": ens["name"], "fetched_at": _now_iso(),
                                                "url": r.url, "status": r.status, "body": r.json()})
