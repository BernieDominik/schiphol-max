"""HTTP with retries, a polite user agent and Open-Meteo's free-tier limits."""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass

import requests

from .config import Config


class FetchError(RuntimeError):
    pass


@dataclass
class Response:
    url: str
    status: int
    text: str
    headers: dict[str, str]
    content: bytes

    def json(self):
        import json
        return json.loads(self.text)


class Http:
    def __init__(self, cfg: Config):
        c = cfg["collection"]
        self.session = requests.Session()
        self.session.headers["User-Agent"] = c["user_agent"]
        self.per_minute = c["openmeteo_calls_per_minute"]
        self.per_hour = c["openmeteo_calls_per_hour"]
        self.min_interval = c.get("openmeteo_min_interval_s", 0.0)
        self._om_calls: deque[float] = deque()

    def _throttle_openmeteo(self, weight: float = 1.0) -> None:
        if self._om_calls and self.min_interval:
            wait = self.min_interval - (time.time() - self._om_calls[-1])
            if wait > 0:
                time.sleep(wait)
        now = time.time()
        while self._om_calls and now - self._om_calls[0] > 3600:
            self._om_calls.popleft()
        last_minute = sum(1 for t in self._om_calls if now - t < 60)
        if last_minute >= self.per_minute:
            time.sleep(60 - (now - self._om_calls[-self.per_minute]) + 0.5)
        if len(self._om_calls) >= self.per_hour:
            time.sleep(3600 - (now - self._om_calls[0]) + 1)
        for _ in range(max(1, int(round(weight)))):
            self._om_calls.append(time.time())

    def get(self, url: str, params: dict | None = None, *, openmeteo: bool = False, weight: float = 1.0,
            retries: int = 5, timeout: int = 60, ok_statuses: tuple[int, ...] = (200,)) -> Response:
        """GET with retries. Statuses in `ok_statuses` are returned; 429/5xx/network errors are retried."""
        delay = 5.0
        last = None
        for attempt in range(retries):
            if openmeteo:
                self._throttle_openmeteo(weight)
            try:
                r = self.session.get(url, params=params, timeout=timeout)
            except requests.RequestException as exc:
                last = f"{type(exc).__name__}: {exc}"
            else:
                if r.status_code in ok_statuses:
                    return Response(r.url, r.status_code, r.text, dict(r.headers), r.content)
                last = f"HTTP {r.status_code}: {r.text[:300]}"
                if r.status_code == 429:
                    time.sleep(90 * (attempt + 1))
                    continue
                if r.status_code < 500:
                    raise FetchError(f"{url} -> {last}")
            time.sleep(delay)
            delay *= 2
        raise FetchError(f"{url} -> {last}")
