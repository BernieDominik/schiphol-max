"""Time helpers. All timestamps are stored as UTC (A5); the target day is an Amsterdam calendar day."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

UTC = timezone.utc
AMS = ZoneInfo("Europe/Amsterdam")
HOUR = 3600

SEASONS = {12: "DJF", 1: "DJF", 2: "DJF", 3: "MAM", 4: "MAM", 5: "MAM",
           6: "JJA", 7: "JJA", 8: "JJA", 9: "SON", 10: "SON", 11: "SON"}


def season(day: date) -> str:
    return SEASONS[day.month]


def to_ts(dt: datetime) -> int:
    if dt.tzinfo is None:
        raise ValueError("naive datetime")
    return int(dt.timestamp())


def from_ts(ts: int | float) -> datetime:
    return datetime.fromtimestamp(ts, UTC)


def iso_z(ts: int | float) -> str:
    return from_ts(ts).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(s: str) -> datetime:
    """Parse ISO text; 'Z' or an offset is required unless the value is a bare date."""
    s = s.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        raise ValueError(f"timestamp without zone: {s}")
    return dt


def parse_ts(s: str) -> int:
    return to_ts(parse_iso(s))


def local_at(day: date, hhmm: str) -> datetime:
    """Aware datetime for a wall-clock time on an Amsterdam day."""
    hh, mm = (int(x) for x in hhmm.split(":"))
    return datetime.combine(day, time(hh, mm), AMS)


def local_ts(day: date, hhmm: str) -> int:
    return to_ts(local_at(day, hhmm))


def day_bounds(day: date) -> tuple[int, int]:
    """UTC unix seconds [start, end) of an Amsterdam calendar day (23, 24 or 25 hours)."""
    start = datetime.combine(day, time(0), AMS)
    end = datetime.combine(day + timedelta(days=1), time(0), AMS)
    return to_ts(start), to_ts(end)


def day_hours(day: date) -> list[int]:
    """Whole UTC hours whose start lies inside the Amsterdam day."""
    start, end = day_bounds(day)
    return list(range(start, end, HOUR))


def local_date(ts: int | float) -> date:
    return from_ts(ts).astimezone(AMS).date()


def local_str(ts: int | float, fmt: str = "%Y-%m-%d %H:%M") -> str:
    return from_ts(ts).astimezone(AMS).strftime(fmt)


def daterange(start: date, end: date):
    """Days from start to end inclusive."""
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def to_date(x: str | date) -> date:
    return x if isinstance(x, date) else date.fromisoformat(x)
