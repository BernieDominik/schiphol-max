"""Self-advancing milestones: counting clean days."""

from datetime import date, datetime, timedelta, timezone

from schiphol_max import milestones as M
from schiphol_max.config import load_config

CFG = load_config()


def state_with(days: dict) -> dict:
    return {"days": days, "overrides": {}, "events": [], "m0_m7_passed": None, "same_day_from": None,
            "soak_start": None, "soak_passed": None, "streak": 0}


def test_streak_counts_back_until_a_bad_or_missing_day():
    good = {"collection_problems": 0, "reproduced": "ok"}
    days = {(date(2026, 10, 8) + timedelta(days=i)).isoformat(): dict(good) for i in range(10)}
    days["2026-10-12"]["collection_problems"] = 1
    s = state_with(days)
    assert M.streak(s, date(2026, 10, 17), date(2026, 10, 8)) == 5        # 13..17
    assert M.streak(s, date(2026, 10, 11), date(2026, 10, 8)) == 4        # 8..11
    s["days"]["2026-10-16"]["reproduced"] = "2 differences"
    assert M.streak(s, date(2026, 10, 17), date(2026, 10, 8)) == 1
    assert M.streak(s, date(2026, 10, 20), date(2026, 10, 8)) == 0        # missing days are not good


def test_same_day_runs_switch_on_only_after_seven_clean_days():
    good = {"collection_problems": 0, "reproduced": "ok"}
    days = {(date(2026, 10, 8) + timedelta(days=i)).isoformat(): dict(good) for i in range(6)}
    s = state_with(days)
    now = datetime(2026, 10, 14, 6, 0, tzinfo=timezone.utc)
    status = M.advance(CFG, s, now, get_ctx=None, log=print)
    assert "6/7" in status and s["same_day_from"] is None
    assert M.effective_runs(CFG, s) == ["evening"]
    s["same_day_from"] = "2026-10-15T05:07:00Z"
    assert M.effective_runs(CFG, s) == ["evening", "early", "morning", "noon", "afternoon"]
