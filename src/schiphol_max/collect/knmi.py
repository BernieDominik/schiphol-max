"""KNMI official daily maximum for station 240 (TX in 0.1 °C, TXH = hour slot in UT). Reference only.

The script download at daggegevens.knmi.nl is announced to close at the end of 2026; from then on
`collect_knmi_recent` switches to the KNMI Data Platform (see `kdp_*` below).
"""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta

from ..config import Config
from ..net import FetchError, Http
from ..rawstore import raw_path, write_raw
from ..timeutil import UTC

DAGGEGEVENS_URL = "https://www.daggegevens.knmi.nl/klimatologie/daggegevens"
KDP_URL = "https://api.dataplatform.knmi.nl/open-data/v1/datasets/{dataset}/versions/{version}/files"
DAGGEGEVENS_CLOSES = date(2027, 1, 1)


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch_daggegevens(cfg: Config, http: Http, start: date, end: date, name: str) -> bool:
    if raw_path(cfg, "knmi_daily", start, name).exists():
        return False
    params = {"stns": cfg["location"]["knmi_station"], "vars": "TX:TXH",
              "start": f"{start:%Y%m%d}", "end": f"{end:%Y%m%d}", "fmt": "json"}
    r = http.get(DAGGEGEVENS_URL, params, timeout=300)
    write_raw(cfg, "knmi_daily", start, name,
              {"source": "knmi_daily", "fetched_at": _now(), "url": r.url, "status": r.status, "body": r.json()})
    return True


def backfill_knmi(cfg: Config, http: Http, end: date, log=print) -> None:
    for s, e in [(date(1951, 1, 1), date(1989, 12, 31)), (date(1990, 1, 1), date(2015, 12, 31)),
                 (date(2016, 1, 1), end)]:
        if fetch_daggegevens(cfg, http, s, e, f"history_{s:%Y%m%d}_{e:%Y%m%d}"):
            log(f"KNMI {s} → {e} stored")


def collect_knmi_recent(cfg: Config, http: Http, today: date) -> str | None:
    """Last 14 days once a day (values arrive 1–2 days late and may be revised for up to two weeks)."""
    if today < DAGGEGEVENS_CLOSES:
        try:
            fetch_daggegevens(cfg, http, today - timedelta(days=14), today, f"recent_{today:%Y%m%d}")
            return
        except FetchError:
            if today < DAGGEGEVENS_CLOSES - timedelta(days=30):
                raise
    return kdp_collect(cfg, http, today)


def kdp_collect(cfg: Config, http: Http, today: date) -> str | None:
    """KNMI Data Platform daily station data. Needs KNMI_API_KEY (a free key from developer.dataplatform.knmi.nl,
    or KNMI's published anonymous key). Stores the raw file listing and newest daily file metadata."""
    key = os.environ.get("KNMI_API_KEY")
    if not key:
        return "skipped: KNMI's script download has closed and no KNMI_API_KEY is set (reference series only)"
    dataset, version = "daggegevens_knmi_stations", "1.0"  # verify name on the portal when switching
    r = http.get(KDP_URL.format(dataset=dataset, version=version),
                 {"maxKeys": 20, "orderBy": "created", "sorting": "desc"})
    write_raw(cfg, "knmi_daily", today, f"kdp_listing_{today:%Y%m%d}",
              {"source": "knmi_kdp", "fetched_at": _now(), "url": r.url, "status": r.status, "body": r.json()})
