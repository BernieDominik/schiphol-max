"""Job log lines (start / success / failure) and alerts.

Alerts reach a person three ways: the GitHub job fails (GitHub emails the owner), an optional
healthchecks.io check gets a /fail ping with the message (and a heartbeat on every successful run,
so silence is noticed too), and the message is appended to data/logs.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

import requests

from .config import Config
from .timeutil import UTC


class Journal:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.alerts: list[str] = []
        self.dir = cfg.root / "data" / "logs"

    def log(self, job: str, event: str, detail: str = "") -> None:
        now = datetime.now(UTC)
        line = {"ts": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "job": job, "event": event, "detail": detail[:2000]}
        print(f"[{line['ts']}] {job} {event} {detail}".rstrip(), flush=True)
        self.dir.mkdir(parents=True, exist_ok=True)
        with open(self.dir / f"{now:%Y-%m}.jsonl", "a") as fh:
            fh.write(json.dumps(line) + "\n")

    def alert(self, message: str) -> None:
        self.alerts.append(message)
        self.log("alert", "raised", message)

    def run(self, job: str, fn, *args, alert: bool = True, **kwargs) -> tuple[bool, object]:
        """Run one job with start/success/failure log lines. Failures alert unless `alert=False`
        (collection jobs, which alert only after two failures in a row, A6)."""
        self.log(job, "start")
        try:
            out = fn(*args, **kwargs)
        except Exception as exc:  # every failure is logged, never swallowed silently
            self.log(job, "failure", f"{type(exc).__name__}: {exc}")
            if alert:
                self.alert(f"{job} failed: {type(exc).__name__}: {exc}")
            return False, None
        self.log(job, "success", "" if out is None else str(out)[:500])
        return True, out

    def finish(self) -> int:
        url = os.environ.get("HEALTHCHECKS_URL")
        if url:
            try:
                if self.alerts:
                    requests.post(url.rstrip("/") + "/fail", data="\n".join(self.alerts).encode(), timeout=20)
                else:
                    requests.post(url, data=b"ok", timeout=20)
            except requests.RequestException as exc:
                print(f"healthchecks ping failed: {exc}")
        return 1 if self.alerts else 0


def load_state(cfg: Config) -> dict:
    p = cfg.root / "data" / "state" / "sources.json"
    return json.loads(p.read_text()) if p.exists() else {}


def save_state(cfg: Config, state: dict) -> None:
    p = cfg.root / "data" / "state" / "sources.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state, indent=1, sort_keys=True) + "\n")


__all__ = ["Journal", "load_state", "save_state", "Path"]
