"""Hand-entered Weather Underground daily maximum (the target). WU's terms forbid automated reading,
so values are typed in; each entry is a new raw file, never an edit."""

from __future__ import annotations

from datetime import date, datetime

from ..config import Config
from ..rawstore import write_raw
from ..timeutil import UTC


def enter_wu_value(cfg: Config, day: date, value_c: int, entered_by: str = "manual", note: str = "") -> str:
    now = datetime.now(UTC)
    payload = {"source": "wu_target", "target_day": day.isoformat(), "value_c": int(value_c),
               "entered_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "entered_by": entered_by, "note": note}
    path = write_raw(cfg, "wu_target", day, f"{day:%Y%m%d}_{now:%Y%m%dT%H%M%S}", payload)
    if path is None:
        raise RuntimeError("an entry with the same timestamp already exists; try again")
    return str(path)
