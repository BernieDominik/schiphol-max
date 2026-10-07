"""Schiphol airport reports (METAR): IEM archive (history, archive of record) and NOAA AWC (live, receipt times).

IEM labels Schiphol's :25 reports as 'specials' (report_type 4), so both report types are requested.
Times are requested in UTC because IEM's local timestamps repeat on the autumn clock-change night.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from ..config import Config
from ..net import Http
from ..rawstore import raw_path, write_raw
from ..timeutil import UTC

IEM_URL = "https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py"
AWC_URL = "https://aviationweather.gov/api/data/metar"


def _now() -> datetime:
    return datetime.now(UTC)


def fetch_iem(cfg: Config, http: Http, start: date, end: date, name: str | None = None) -> bool:
    """IEM reports for UTC days [start, end]. Returns True if a new raw file was written."""
    name = name or f"{start:%Y%m%d}_{end:%Y%m%d}"
    if raw_path(cfg, "iem_metar", start, name).exists():
        return False
    params = [("station", cfg["location"]["icao"]), ("data", "tmpc"), ("data", "metar"),
              ("tz", "Etc/UTC"), ("format", "onlycomma"), ("latlon", "no"), ("elev", "no"),
              ("missing", "M"), ("trace", "T"), ("direct", "no"), ("report_type", "3"), ("report_type", "4"),
              ("sts", f"{start.isoformat()}T00:00Z"), ("ets", f"{(end + timedelta(days=1)).isoformat()}T00:00Z")]
    r = http.get(IEM_URL, params, timeout=300)
    write_raw(cfg, "iem_metar", start, name,
              {"source": "iem_metar", "fetched_at": _now().strftime("%Y-%m-%dT%H:%M:%SZ"),
               "url": r.url, "status": r.status, "body": r.text})
    return True


def backfill_iem(cfg: Config, http: Http, end: date, log=print) -> None:
    first = date.fromisoformat(cfg["target"]["history_from"]) - timedelta(days=1)
    for year in range(first.year, end.year + 1):
        s = max(first, date(year, 1, 1))
        e = min(end, date(year, 12, 31))
        if fetch_iem(cfg, http, s, e):
            log(f"IEM {s} → {e} stored")


def collect_iem_recent(cfg: Config, http: Http, now: datetime | None = None) -> None:
    """The archive of record for the last three UTC days, once a day (AWC covers the hours in between)."""
    now = now or _now()
    end = now.date()
    fetch_iem(cfg, http, end - timedelta(days=2), end, name=f"recent_{now:%Y%m%d}")


def collect_awc(cfg: Config, http: Http, now: datetime | None = None) -> None:
    """Latest reports with their receipt times (about 2–3 minutes after observation)."""
    now = now or _now()
    name = f"awc_{now:%Y%m%dT%H%M}"
    if raw_path(cfg, "awc_metar", now.date(), name).exists():
        return
    r = http.get(AWC_URL, {"ids": cfg["location"]["icao"], "format": "json", "hours": 8}, ok_statuses=(200, 204))
    body = r.json() if r.status == 200 and r.text.strip() else []
    write_raw(cfg, "awc_metar", now.date(), name,
              {"source": "awc_metar", "fetched_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
               "url": r.url, "status": r.status, "body": body})
