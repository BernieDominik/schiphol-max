"""DWD MOSMIX_L for station 06240: a ready-made corrected forecast, used only as an outside benchmark.
DWD keeps about two days of runs, so every new file is saved as soon as it is seen."""

from __future__ import annotations

import base64
import io
import re
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime

from ..config import Config
from ..net import Http
from ..rawstore import raw_path, write_raw
from ..timeutil import UTC, parse_ts

BASE = "https://opendata.dwd.de/weather/local_forecasts/mos/MOSMIX_L/single_stations/{wmo}/kml/"
NS = {"dwd": "https://opendata.dwd.de/weather/lib/pointforecast_dwd_extension_V1_0.xsd",
      "kml": "http://www.opengis.net/kml/2.2"}


def collect_mosmix(cfg: Config, http: Http) -> list[str]:
    wmo = cfg["location"]["wmo_station"]
    url = BASE.format(wmo=wmo)
    listing = http.get(url).text
    new = []
    for stamp in sorted(set(re.findall(rf"MOSMIX_L_(\d{{10}})_{wmo}\.kmz", listing))):
        issued = datetime.strptime(stamp, "%Y%m%d%H").replace(tzinfo=UTC)
        name = f"MOSMIX_L_{stamp}"
        if raw_path(cfg, "mosmix", issued.date(), name).exists():
            continue
        r = http.get(url + f"MOSMIX_L_{stamp}_{wmo}.kmz")
        write_raw(cfg, "mosmix", issued.date(), name,
                  {"source": "mosmix", "issued": issued.strftime("%Y-%m-%dT%H:%M:%SZ"),
                   "fetched_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                   "last_modified": r.headers.get("Last-Modified"), "url": r.url,
                   "kmz_base64": base64.b64encode(r.content).decode()})
        new.append(stamp)
    return new


def parse_mosmix(kmz_base64: str) -> dict:
    """Returns {'issue': ts, 'times': [ts...], 'TTT': [°C...], 'TX': [°C or None...]}."""
    with zipfile.ZipFile(io.BytesIO(base64.b64decode(kmz_base64))) as z:
        xml = z.read(z.namelist()[0])
    root = ET.fromstring(xml)
    issue = parse_ts(root.find(".//dwd:IssueTime", NS).text)
    times = [parse_ts(t.text) for t in root.findall(".//dwd:ForecastTimeSteps/dwd:TimeStep", NS)]
    out = {"issue": issue, "times": times}
    for fc in root.findall(".//dwd:Forecast", NS):
        name = fc.get("{https://opendata.dwd.de/weather/lib/pointforecast_dwd_extension_V1_0.xsd}elementName")
        if name in ("TTT", "TX"):
            vals = fc.find("dwd:value", NS).text.split()
            out[name] = [None if v == "-" else round(float(v) - 273.15, 2) for v in vals]
    return out
