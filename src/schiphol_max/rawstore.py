"""Append-only raw store (A3): one gzipped JSON file per fetch, never overwritten or deleted."""

from __future__ import annotations

import gzip
import json
import os
import tempfile
from datetime import date
from pathlib import Path
from typing import Any, Iterator

from .config import Config


def raw_path(cfg: Config, source: str, day: date, name: str) -> Path:
    return cfg.raw_dir / source / f"{day:%Y}" / f"{day:%m}" / f"{day:%d}" / f"{name}.json.gz"


def write_once(path: Path, payload: Any, sort_keys: bool = True) -> bool:
    """Create `path` with JSON content. Returns False (and writes nothing) if it already exists."""
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(payload, sort_keys=sort_keys, separators=(",", ":"), ensure_ascii=False).encode()
    blob = gzip.compress(data, mtime=0) if path.suffix == ".gz" else data
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(blob)
        try:
            os.link(tmp, path)  # atomic and fails if the target exists
        except FileExistsError:
            return False
    finally:
        os.unlink(tmp)
    return True


def read_json(path: Path) -> Any:
    raw = path.read_bytes()
    if path.suffix == ".gz":
        raw = gzip.decompress(raw)
    return json.loads(raw)


def write_raw(cfg: Config, source: str, day: date, name: str, payload: dict) -> Path | None:
    path = raw_path(cfg, source, day, name)
    return path if write_once(path, payload) else None


def iter_raw(cfg: Config, source: str) -> Iterator[Path]:
    base = cfg.raw_dir / source
    if not base.exists():
        return iter(())
    return iter(sorted(base.rglob("*.json.gz")))
