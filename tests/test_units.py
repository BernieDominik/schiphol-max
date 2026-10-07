"""Fast unit tests that need no downloaded data."""

from datetime import date, timedelta

import numpy as np
import pytest

from schiphol_max import calibrate
from schiphol_max.blend import inverse_mae_weights, mlpol_weights
from schiphol_max.config import load_config
from schiphol_max.correct import fit_correction, predict
from schiphol_max.derived import metar_temperature, normalize_report
from schiphol_max.deviation import against_standard, standard_forecast
from schiphol_max.learn import running_bias
from schiphol_max.rawstore import read_json, write_once
from schiphol_max.schedule import slots_between
from schiphol_max.timeutil import day_bounds, day_hours, from_ts, local_ts, AMS

CFG = load_config()
CAL = CFG["calibration"]


def test_day_lengths_on_clock_change_days():
    assert len(day_hours(date(2026, 10, 25))) == 25
    assert len(day_hours(date(2027, 3, 28))) == 23
    assert len(day_hours(date(2027, 1, 15))) == 24
    s, e = day_bounds(date(2027, 1, 15))
    assert from_ts(s).hour == 23 and from_ts(e).hour == 23


@pytest.mark.parametrize("day", [date(2026, 10, 25), date(2027, 3, 28), date(2027, 1, 15)])
def test_every_slot_fires_exactly_once(day):
    start = local_ts(day, "00:00") - 1
    end = local_ts(day + timedelta(days=1), "00:00") - 1
    slots = slots_between(CFG, start, end)
    names = [s.name for s in slots]
    assert len(names) == len(set(names))
    assert names.count("settle") == 1 and names.count("completeness") == 1
    assert sorted(n.split(":")[1] for n in names if n.startswith("forecast")) == sorted(CFG["schedule"]["forecast_runs"])
    for s in slots:
        h = from_ts(s.ts).astimezone(AMS).hour
        assert not (2 <= h < 3), "nothing may be scheduled in the clock-change hour"


def test_metar_temperature_parsing():
    assert metar_temperature("EHAM 051655Z 26009KT 220V280 9999 FEW010 SCT014 17/15 Q1021 NOSIG") == 17
    assert metar_temperature("EHAM 022225Z 11003KT 9999 MIFG NSC M01/M03 Q1031 NOSIG") == -1
    assert metar_temperature("EHAM 022225Z 11003KT 9999 M00/M01 Q1031") == 0
    assert metar_temperature("EHAM 022225Z 11003KT 9999 ///// Q1031") is None
    assert normalize_report("METAR EHAM 051655Z 26009KT 17/15 Q1021=") == "EHAM 051655Z 26009KT 17/15 Q1021"


def test_probabilities_sum_floor_and_table():
    for mu, sigma in [(16.9, 1.28), (0.5, 0.8), (31.4, 2.5), (-3.2, 3.1)]:
        p = calibrate.degree_probabilities(mu, sigma, CAL)
        assert abs(sum(p.values()) - 1) < 1e-9
        assert min(p.values()) >= CAL["floor_probability"] - 1e-4
        assert all(abs(k - mu) <= 8 for k in p)
        top = calibrate.top_degree(p, mu)
        table, outside = calibrate.five_degree_table(p, top, 4)
        assert [t["degree"] for t in table] == list(range(top - 2, top + 3))
        assert abs(outside - (1 - sum(t["probability"] for t in table))) < 1e-9


def test_same_day_floor_below_max_so_far():
    p = calibrate.degree_probabilities(18.2, 1.0, CAL, max_so_far=19)
    below = sum(v for k, v in p.items() if k < 19)
    assert abs(below - CAL["below_max_total"]) <= 0.0005
    assert abs(sum(p.values()) - 1) < 1e-9
    top = calibrate.top_degree(p, 18.2)
    assert top >= 19
    table, _ = calibrate.five_degree_table(p, top, 4)
    assert len(table) == 5


def test_standard_forecast_rounds_half_up():
    assert standard_forecast([16.5, 16.5]) == 17
    assert standard_forecast([16.44, 16.46]) == 16
    assert standard_forecast([-0.5]) == 0
    dev = against_standard({15: 0.2, 16: 0.5, 17: 0.3}, 16, 2)
    assert dev["p_above_standard"] == 0.3 and dev["p_on_standard"] == 0.5 and dev["p_miss_2_or_more"] == 0


def test_running_bias_closed_form_matches_recursion():
    rng = np.random.default_rng(0)
    e = rng.normal(0.4, 1, 300)
    w = np.full(300, 0.03)
    w[100:130] = 0.10
    r = 0.0
    for ei, wi in zip(e, w):
        r = (1 - wi) * r + wi * ei
    assert abs(running_bias(e, w) - r) < 1e-12


def test_correction_shrinks_toward_trusting_the_model():
    rng = np.random.default_rng(1)
    x = rng.uniform(-5, 35, 400)
    doy = rng.integers(1, 366, 400)
    y = x + 1.0 + rng.normal(0, 0.8, 400)
    p = fit_correction(x, y, doy, alpha=1.0, seasonal_after=365)
    assert abs(p["b"] - 1) < 0.05 and abs(p["a"] - 1.0) < 0.3 and p["seasonal"]
    # extrapolates above the training range (D5: no tree learners)
    assert predict(p, 45.0, 200) > 44


def test_weights():
    w = inverse_mae_weights({"a": 1.0, "b": 2.0})
    assert abs(w["a"] - 2 / 3) < 1e-9
    hist = [({"good": 10.0 + i % 3, "bad": 14.0}, 10.0 + i % 3) for i in range(200)]
    w = mlpol_weights(hist, ["good", "bad"])
    assert w["good"] > 0.9 and abs(sum(w.values()) - 1) < 1e-9


def test_write_once(tmp_path):
    p = tmp_path / "a" / "x.json.gz"
    assert write_once(p, {"v": 1})
    assert not write_once(p, {"v": 2})
    assert read_json(p) == {"v": 1}
