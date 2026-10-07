"""Configuration: one YAML file holds every tuning value (PRD coding rule)."""

from __future__ import annotations

import copy
import os
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class ModelSpec:
    name: str
    openmeteo: str
    publish_dir: str
    run_hours: tuple[int, ...]
    horizon_h: dict[int, int]
    single_runs_from: str
    previous_runs_from: str
    delay_h: float
    collect: bool
    blend: bool
    previous_run_every_h: int | None = None


class Config:
    """Thin wrapper around the YAML dict with a few derived helpers."""

    def __init__(self, raw: dict[str, Any], root: Path, data_dir: Path | None = None):
        self.raw = raw
        self.root = root
        self.data_dir = data_dir or root / "data"

    def __getitem__(self, key: str) -> Any:
        return self.raw[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self.raw.get(key, default)

    @cached_property
    def models(self) -> dict[str, ModelSpec]:
        out = {}
        for name, m in self.raw["models"].items():
            out[name] = ModelSpec(
                name=name,
                openmeteo=m["openmeteo"],
                publish_dir=m["publish_dir"],
                run_hours=tuple(m["run_hours"]),
                horizon_h={int(k): int(v) for k, v in m["horizon_h"].items()},
                single_runs_from=m["single_runs_from"],
                previous_runs_from=m["previous_runs_from"],
                delay_h=float(m["delay_h"]),
                collect=bool(m.get("collect", True)),
                blend=bool(m.get("blend", True)),
                previous_run_every_h=m.get("previous_run_every_h"),
            )
        return out

    @property
    def collect_models(self) -> list[str]:
        return [n for n, m in self.models.items() if m.collect]

    @property
    def blend_models(self) -> list[str]:
        return [n for n, m in self.models.items() if m.blend]

    @property
    def tz(self) -> str:
        return self.raw["location"]["timezone"]

    @property
    def raw_dir(self) -> Path:
        return self.root / "data" / "raw"

    @property
    def records_dir(self) -> Path:
        return self.data_dir / "records"

    @property
    def params_dir(self) -> Path:
        return self.data_dir / "params"

    @property
    def db_path(self) -> Path:
        return self.root / "data" / "schiphol.sqlite"

    @property
    def reports_dir(self) -> Path:
        # Official reports live at the repo root; backtest variants keep theirs next to their data.
        if self.data_dir == self.root / "data":
            return self.root / "reports"
        return self.data_dir / "reports"

    def with_overrides(self, overrides: dict[str, Any], data_dir: Path | None = None) -> "Config":
        raw = copy.deepcopy(self.raw)
        for dotted, value in overrides.items():
            node = raw
            keys = dotted.split(".")
            for k in keys[:-1]:
                node = node.setdefault(k, {})
            node[keys[-1]] = value
        return Config(raw, self.root, data_dir or self.data_dir)


def load_config(path: Path | None = None, data_dir: Path | None = None) -> Config:
    root = Path(os.environ.get("SMAX_ROOT", REPO_ROOT))
    path = path or root / "config.yaml"
    with open(path) as fh:
        raw = yaml.safe_load(fh)
    return Config(raw, root, data_dir)


def code_version(root: Path = REPO_ROOT) -> str:
    """Fingerprint of the code that makes forecasts: the package source, config.yaml and the lockfile.
    It changes only when they change (not when the hourly job commits data), and needs no git history."""
    import hashlib

    h = hashlib.sha256()
    files = sorted((root / "src").rglob("*.py")) + [root / "config.yaml", root / "uv.lock"]
    for p in files:
        if p.exists():
            h.update(str(p.relative_to(root)).encode())
            h.update(p.read_bytes())
    return h.hexdigest()[:7]
