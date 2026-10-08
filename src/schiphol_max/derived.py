"""Derived store: one SQLite database rebuilt from the raw store at any time (A3).

Ingestion is incremental: raw files never change, so a file's path identifies its content.
`smax rebuild --full` deletes the database and recreates it from scratch.
"""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path

from .collect.mosmix import parse_mosmix
from .config import Config
from .rawstore import iter_raw, read_json
from .timeutil import UTC, parse_ts, to_ts

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS ingested(path TEXT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS single_run(model TEXT, run INTEGER, fetched_at INTEGER, status TEXT,
    PRIMARY KEY(model, run));
CREATE TABLE IF NOT EXISTS single_hourly(model TEXT, run INTEGER, valid INTEGER, temp REAL,
    PRIMARY KEY(model, run, valid)) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS prev_hourly(model TEXT, valid INTEGER, n INTEGER, temp REAL, fetched_at INTEGER,
    PRIMARY KEY(model, valid, n)) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS publish(model TEXT, run INTEGER, published INTEGER, source TEXT, recorded_at INTEGER,
    PRIMARY KEY(model, run, source));
CREATE TABLE IF NOT EXISTS metar(obs INTEGER, report TEXT, temp INTEGER, source TEXT, receipt INTEGER,
    first_seen INTEGER, PRIMARY KEY(obs, report));
CREATE TABLE IF NOT EXISTS knmi(day TEXT PRIMARY KEY, tx REAL, txh INTEGER, fetched_at INTEGER);
CREATE TABLE IF NOT EXISTS mosmix(issue INTEGER, valid INTEGER, ttt REAL, tx REAL, published INTEGER,
    PRIMARY KEY(issue, valid));
CREATE TABLE IF NOT EXISTS wu(path TEXT PRIMARY KEY, day TEXT, value INTEGER, entered_at INTEGER);
CREATE TABLE IF NOT EXISTS fetch_log(source TEXT, name TEXT, fetched_at INTEGER, status TEXT,
    PRIMARY KEY(source, name));
"""

TEMP_TOKEN = re.compile(r"^(M?\d\d)/(M?\d\d|//)?$")


SCHEMA_VERSION = "3"


def connect(cfg: Config) -> sqlite3.Connection:
    """Open the derived database; an older layout is deleted and rebuilt from the raw store."""
    cfg.db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(cfg.db_path)
    try:
        version = con.execute("SELECT value FROM meta WHERE key='schema'").fetchone()
    except sqlite3.OperationalError:
        version = None
    has_tables = con.execute("SELECT count(*) FROM sqlite_master WHERE type='table'").fetchone()[0]
    if has_tables and (version is None or version[0] != SCHEMA_VERSION):
        con.close()
        cfg.db_path.unlink()
        con = sqlite3.connect(cfg.db_path)
    con.executescript(SCHEMA)
    con.execute("INSERT OR REPLACE INTO meta VALUES ('schema', ?)", (SCHEMA_VERSION,))
    return con


def normalize_report(text: str) -> str:
    t = text.strip().rstrip("=").strip()
    for prefix in ("METAR ", "SPECI "):
        if t.startswith(prefix):
            t = t[len(prefix):]
    return " ".join(t.split())


def metar_temperature(report: str) -> int | None:
    """Whole °C from the temperature group, e.g. '17/12' -> 17, 'M01/M03' -> -1, 'M00/...' -> 0."""
    tokens = report.split()
    for tok in tokens[2:]:
        if tok == "RMK":
            break
        m = TEMP_TOKEN.match(tok)
        if m:
            t = m.group(1)
            return -int(t[1:]) if t.startswith("M") else int(t)
    return None


def _ts(s: str | None) -> int | None:
    return parse_ts(s) if s else None


def _http_date(s: str | None) -> int | None:
    if not s:
        return None
    try:
        return to_ts(parsedate_to_datetime(s))
    except (TypeError, ValueError):
        return None


def _ingest_file(con: sqlite3.Connection, source_dir: str, path: Path, rel: str) -> None:
    d = read_json(path)
    src = d.get("source", source_dir)
    fetched = _ts(d.get("fetched_at"))
    if src == "single_runs":
        model, run = d["model"], parse_ts(d["run"])
        body = d.get("body") or {}
        status = "ok" if body else "unavailable"
        # fetched_at is when we first held the run's data (a later 'unavailable' marker never overrides it).
        con.execute("""INSERT INTO single_run VALUES (?,?,?,?) ON CONFLICT(model, run) DO UPDATE SET
                       fetched_at=CASE WHEN single_run.status='ok' THEN single_run.fetched_at ELSE excluded.fetched_at END,
                       status=CASE WHEN single_run.status='ok' THEN 'ok' ELSE excluded.status END""",
                    (model, run, fetched, status))
        hourly = body.get("hourly") or {}
        times, temps = hourly.get("time") or [], hourly.get("temperature_2m") or []
        con.executemany("INSERT OR REPLACE INTO single_hourly VALUES (?,?,?,?)",
                        [(model, run, int(t), float(v)) for t, v in zip(times, temps) if v is not None])
    elif src == "previous_runs":
        model = d["model"]
        hourly = d["body"]["hourly"]
        times = hourly.get("time") or []
        rows = []
        for n in range(0, 8):
            key = "temperature_2m" if n == 0 else f"temperature_2m_previous_day{n}"
            vals = hourly.get(key) or []
            rows += [(model, int(t), n, float(v), fetched) for t, v in zip(times, vals) if v is not None]
        con.executemany("""INSERT INTO prev_hourly VALUES (?,?,?,?,?)
                           ON CONFLICT(model, valid, n) DO UPDATE SET temp=excluded.temp, fetched_at=excluded.fetched_at
                           WHERE excluded.fetched_at >= prev_hourly.fetched_at""", rows)
    elif src == "publish_times":
        model = d["model"]
        con.executemany("""INSERT INTO publish VALUES (?,?,?,?,?) ON CONFLICT(model, run, source) DO UPDATE SET
                           recorded_at=min(publish.recorded_at, excluded.recorded_at)""",
                        [(model, parse_ts(run), parse_ts(mod), "bucket", fetched) for run, mod in d["runs"].items()])
    elif src == "latest_runs":
        for item in d["models"]:
            if item.get("reference_time") and item.get("last_modified"):
                run = parse_ts(item["reference_time"])
                pub = _http_date(item["last_modified"])
                con.execute("""INSERT INTO publish VALUES (?,?,?,?,?) ON CONFLICT(model, run, source)
                               DO UPDATE SET published=min(published, excluded.published),
                                             recorded_at=min(recorded_at, excluded.recorded_at)""",
                            (item["model"], run, pub, "latest", fetched))
    elif src == "iem_metar":
        rows = []
        for line in d["body"].splitlines()[1:]:
            parts = line.split(",", 3)          # station, valid, tmpc, metar
            if len(parts) < 4 or "IEM_DS3505" in parts[3]:
                continue  # not a genuine airport report (rebuilt hourly synoptic row)
            obs = to_ts(datetime.strptime(parts[1], "%Y-%m-%d %H:%M").replace(tzinfo=UTC))
            report = normalize_report(parts[3])
            temp = metar_temperature(report)
            if temp is None and parts[2] not in ("M", ""):
                temp = int(round(float(parts[2])))
            rows.append((obs, report, temp, "iem", None, fetched))
        con.executemany("""INSERT INTO metar VALUES (?,?,?,?,?,?) ON CONFLICT(obs, report)
                           DO UPDATE SET first_seen=min(metar.first_seen, excluded.first_seen)""", rows)
    elif src == "awc_metar":
        rows = []
        for item in d["body"] or []:
            report = normalize_report(item.get("rawOb", ""))
            temp = metar_temperature(report)
            if temp is None and item.get("temp") is not None:
                temp = int(round(item["temp"]))
            receipt = _ts(item.get("receiptTime", "").replace(".000Z", "Z")) if item.get("receiptTime") else None
            rows.append((int(item["obsTime"]), report, temp, "awc", receipt, fetched))
        con.executemany("""INSERT INTO metar VALUES (?,?,?,?,?,?) ON CONFLICT(obs, report)
                           DO UPDATE SET receipt=coalesce(min(metar.receipt, excluded.receipt), metar.receipt, excluded.receipt),
                                         first_seen=min(metar.first_seen, excluded.first_seen)""", rows)
    elif src == "knmi_daily":
        body = d.get("body")
        if isinstance(body, list):
            rows = []
            for item in body:
                if item.get("TX") is None:
                    continue
                day = item["date"][:10]
                rows.append((day, item["TX"] / 10.0, item.get("TXH"), fetched))
            con.executemany("""INSERT INTO knmi VALUES (?,?,?,?) ON CONFLICT(day) DO UPDATE SET
                               tx=excluded.tx, txh=excluded.txh, fetched_at=excluded.fetched_at
                               WHERE excluded.fetched_at >= knmi.fetched_at""", rows)
    elif src == "mosmix":
        m = parse_mosmix(d["kmz_base64"])
        tx = m.get("TX") or [None] * len(m["times"])
        published = _http_date(d.get("last_modified")) or fetched
        con.executemany("INSERT OR REPLACE INTO mosmix VALUES (?,?,?,?,?)",
                        [(m["issue"], t, ttt, x, published) for t, ttt, x in zip(m["times"], m["TTT"], tx)])
    elif src == "wu_target":
        con.execute("INSERT OR REPLACE INTO wu VALUES (?,?,?,?)",
                    (rel, d["target_day"], int(d["value_c"]), parse_ts(d["entered_at"])))
    if fetched is not None:
        con.execute("INSERT OR REPLACE INTO fetch_log VALUES (?,?,?,?)",
                    (src, path.name, fetched, str(d.get("status", ""))))


SOURCES = ["single_runs", "previous_runs", "publish_times", "latest_runs", "iem_metar", "awc_metar",
           "knmi_daily", "mosmix", "wu_target"]


def rebuild(cfg: Config, full: bool = False, log=None) -> int:
    """Ingest every raw file not yet ingested. Returns the number of files ingested."""
    if full and cfg.db_path.exists():
        cfg.db_path.unlink()
    con = connect(cfg)
    done = {r[0] for r in con.execute("SELECT path FROM ingested")}
    count = 0
    for source in SOURCES:
        base = cfg.raw_dir / source
        if not base.exists():
            continue
        for path in sorted(base.rglob("*.json.gz")):
            rel = str(path.relative_to(cfg.raw_dir))
            if rel in done:
                continue
            _ingest_file(con, source, path, rel)
            con.execute("INSERT INTO ingested VALUES (?)", (rel,))
            count += 1
            if count % 2000 == 0:
                con.commit()
                if log:
                    log(f"ingested {count} files")
    con.commit()
    con.close()
    return count


__all__ = ["connect", "rebuild", "metar_temperature", "normalize_report", "iter_raw"]
