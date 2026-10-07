"""The availability rules that enforce no look-ahead, on hand-made data."""

from datetime import date

import numpy as np

from schiphol_max.access import Data, ModelSeries, Run
from schiphol_max.config import load_config
from schiphol_max.timeutil import HOUR, day_bounds, parse_ts

CFG = load_config()


def make_data() -> Data:
    d = object.__new__(Data)
    d.cfg = CFG
    d.margin = 600
    d.metar_delay = 300
    d.published = {}
    d.delay = {("icon_d2", h): 2 * HOUR for h in range(0, 24, 3)}
    d.models = {m: ModelSeries() for m in CFG.models}
    return d


def add_run(d: Data, model: str, run_iso: str, published_iso: str, hours: int = 48, base: float = 10.0):
    run = parse_ts(run_iso)
    valid = np.arange(run, run + hours * HOUR, HOUR, dtype=np.int64)
    d.published[(model, run)] = parse_ts(published_iso)
    ms = d.models[model]
    ms.runs.append(Run(model, run, d.run_available(model, run), valid, np.full(len(valid), base)))
    ms.runs.sort(key=lambda r: r.run)
    ms.run_times = [r.run for r in ms.runs]


def test_newest_run_respects_publish_time_and_coverage():
    d = make_data()
    add_run(d, "icon_d2", "2026-10-07T12:00Z", "2026-10-07T13:30Z", base=11)
    add_run(d, "icon_d2", "2026-10-07T15:00Z", "2026-10-07T16:30Z", base=15)
    start, end = day_bounds(date(2026, 10, 8))
    # 10 minutes after publication + margin: the 15 UTC run is usable
    assert d.newest_run("icon_d2", parse_ts("2026-10-07T16:41Z"), start, end).temp[0] == 15
    # one minute before (publish + 10-minute margin) it is not; the 12 UTC run is used instead
    assert d.newest_run("icon_d2", parse_ts("2026-10-07T16:39Z"), start, end).temp[0] == 11
    # a run that does not cover the whole day is never used (no part-day maximum)
    start2, end2 = day_bounds(date(2026, 10, 9))
    assert d.newest_run("icon_d2", parse_ts("2026-10-08T00:00Z"), start2, end2) is None


def test_previous_runs_source_is_never_older_than_the_truth():
    d = make_data()
    # ICON-EU short runs (03/09/15/21 UTC) do not reach day 1; the true source of day-1 values at 05 UTC is the
    # 00 UTC run, but the rule assumes the newer 03 UTC run, so the availability it assumes is later than reality.
    t = parse_ts("2026-03-10T05:00Z")
    assert d.prev_source_run("icon_eu", t, 1) == parse_ts("2026-03-09T03:00Z")
    # 6-hourly models map to the newest 00/06/12/18 run at or before t − 24 h
    assert d.prev_source_run("gfs", parse_ts("2026-03-10T17:00Z"), 1) == parse_ts("2026-03-09T12:00Z")
    # hourly HARMONIE runs: exactly 24 h before
    assert d.prev_source_run("harmonie_nl", parse_ts("2026-03-10T17:00Z"), 1) == parse_ts("2026-03-09T17:00Z")


def test_reports_are_filtered_by_receipt_not_observation_time():
    d = make_data()
    d.report_obs = np.array([parse_ts("2026-07-01T09:55Z"), parse_ts("2026-07-01T10:25Z")], dtype=np.int64)
    d.report_temp = np.array([25.0, 27.0])
    d.report_avail = np.array([parse_ts("2026-07-01T10:01Z"), parse_ts("2026-07-01T10:31Z")], dtype=np.int64)
    assert d.max_so_far(date(2026, 7, 1), parse_ts("2026-07-01T10:00Z")) is None
    assert d.max_so_far(date(2026, 7, 1), parse_ts("2026-07-01T10:30Z")) == 25
    assert d.max_so_far(date(2026, 7, 1), parse_ts("2026-07-01T10:31Z")) == 27
