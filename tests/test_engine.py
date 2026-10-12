"""Small, fast tests that pin down the method. Run with ``python -m pytest`` or ``python -m unittest``."""

from __future__ import annotations

import datetime as dt
import random
import unittest

from review import analyze, stats
from review.config import load_profile


def _cfg(profile="generic", **rules):
    prof = load_profile(profile)
    r = dict(prof["rules"])
    r.update(rules)
    return {
        "business": {"name": "Test Co", "currency": "USD"},
        "profile": profile,
        "vocabulary": prof["vocabulary"],
        "rules": r,
        "playbooks": prof["playbooks"],
        "measures": {"revenue": "SUM(x)", "orders": "COUNT(*)", "new_customers": "SUM(n)"},
        "extra_dimensions": {},
        "segments": {},
    }


def _rows(end: dt.date, days=120, units=4, unit_mult=None, day_mult=None, seed=1):
    """Flat daily rows with weekday seasonality and small noise. Multipliers plant anomalies."""
    rng = random.Random(seed)
    unit_mult = unit_mult or {}
    day_mult = day_mult or {}
    wk = {0: .9, 1: .9, 2: 1, 3: 1, 4: 1.2, 5: 1.3, 6: .8}
    rows = []
    for k in range(days):
        d = end - dt.timedelta(days=days - 1 - k)
        dm = day_mult.get((end - d).days, 1.0)
        for u in range(units):
            um = unit_mult.get((f"U{u}", (end - d).days), 1.0)
            for ch, share in (("store", .7), ("online", .3)):
                orders = 100 * wk[d.weekday()] * dm * um * share * rng.uniform(.97, 1.03)
                rows.append({"d": d, "unit": f"U{u}", "channel": ch, "revenue": orders * 20, "orders": orders, "new_customers": orders * .25})
    return rows


class StatsTests(unittest.TestCase):
    def test_robust_baseline_ignores_one_outlier(self):
        base = stats.robust_baseline([100, 101, 99, 100, 102, 98, 100, 400])
        self.assertAlmostEqual(base["median"], 100.0, places=1)
        self.assertLess(base["spread"], 5)  # an outlier would blow up a stdev; MAD shrugs

    def test_decomposition_sums_to_delta(self):
        d = stats.decompose(revenue=9000, orders=450, base_revenue=10000, base_orders=500)
        self.assertAlmostEqual(d["volume_effect"] + d["value_effect"], d["delta"])

    def test_same_weekday_dates(self):
        ds = stats.same_weekday_dates(dt.date(2026, 10, 8), 3)
        self.assertTrue(all(x.weekday() == 3 for x in ds))
        self.assertEqual(ds[0], dt.date(2026, 10, 1))


class AnalyzeTests(unittest.TestCase):
    END = dt.date(2026, 10, 8)

    def test_quiet_day_has_no_flags(self):
        res = analyze.analyze(_rows(self.END), self.END, _cfg(min_signal_revenue=100, unit_move_abs=100))
        self.assertTrue(res["data_present"])
        self.assertEqual(res["flags"], [], res["flags"])
        self.assertTrue(res["verdict"].startswith("Normal day"))

    def test_volume_drop_is_flagged_and_persistent(self):
        rows = _rows(self.END, day_mult={0: .85, 1: .9})
        res = analyze.analyze(rows, self.END, _cfg(min_signal_revenue=100, unit_move_abs=100))
        kinds = [f["kind"] for f in res["flags"]]
        self.assertIn("volume_drop", kinds)
        self.assertTrue(res["persistence"]["persistent"])
        self.assertTrue(res["verdict"].startswith("Soft, and it is a trend"))

    def test_one_off_drop_is_not_a_trend(self):
        rows = _rows(self.END, day_mult={0: .85})
        res = analyze.analyze(rows, self.END, _cfg(min_signal_revenue=100, unit_move_abs=100))
        self.assertFalse(res["persistence"]["persistent"])
        self.assertTrue(res["verdict"].startswith("Soft day"))

    def test_unit_drop_marks_yesterday(self):
        rows = _rows(self.END, unit_mult={("U2", 0): .6, ("U2", 1): .6})
        res = analyze.analyze(rows, self.END, _cfg(min_signal_revenue=100, unit_move_abs=100))
        down = res["unit_movers"]["down"]
        self.assertEqual(down[0]["unit"], "U2")
        self.assertTrue(down[0]["persistent"])

    def test_small_moves_below_floor_are_ignored(self):
        rows = _rows(self.END, day_mult={0: .85})
        res = analyze.analyze(rows, self.END, _cfg(min_signal_revenue=10**9, unit_move_abs=10**9))
        self.assertEqual([f for f in res["flags"] if f["kind"] in ("volume_drop", "value_drop")], [])

    def test_missing_day(self):
        res = analyze.analyze(_rows(self.END - dt.timedelta(days=1)), self.END, _cfg())
        self.assertFalse(res["data_present"])
        self.assertTrue(res["warnings"])


if __name__ == "__main__":
    unittest.main()


class HolidayTests(unittest.TestCase):
    """Thanksgiving 2026 is Nov 26; 2025 was Nov 27. Independence Day 2026 is a Saturday."""

    def _cal_cfg(self, **rules):
        from review.holidays import Calendar
        c = _cfg(min_signal_revenue=100, unit_move_abs=100, **rules)
        c["_calendar"] = Calendar.load()
        return c

    def test_calendar_rules(self):
        from review.holidays import Calendar
        c = Calendar.load()
        self.assertEqual(c.lookup(dt.date(2026, 11, 26)), ("Thanksgiving", 0))
        self.assertEqual(c.same_holiday_last_year(dt.date(2026, 11, 26)), dt.date(2025, 11, 27))
        self.assertEqual(c.same_holiday_last_year(dt.date(2026, 7, 4)), dt.date(2025, 7, 4))
        self.assertEqual(c.lookup(dt.date(2026, 4, 5)), ("Easter", 0))
        self.assertIsNone(c.lookup(dt.date(2026, 10, 8)))

    def test_holiday_day_compares_to_same_holiday_last_year(self):
        end = dt.date(2026, 11, 26)
        rows = _rows(end, days=400, day_mult={0: .2, 364: .25})  # both Thanksgivings at ~20%
        res = analyze.analyze(rows, end, self._cal_cfg())
        self.assertEqual(res["holiday"]["name"], "Thanksgiving")
        self.assertEqual(res["holiday"]["ly_date"], "2025-11-27")
        self.assertTrue(res["verdict"].startswith("Thanksgiving"))
        self.assertTrue(res["persistence"]["suspended"])
        kinds = [f["kind"] for f in res["flags"]]
        self.assertNotIn("volume_drop", kinds)   # an 80% drop on a holiday is not a volume drop
        self.assertNotIn("unit_drop", kinds)

    def test_baseline_skips_holidays(self):
        # Review a normal Thursday two weeks after Thanksgiving: the holiday must not be in its baseline.
        end = dt.date(2026, 12, 10)
        rows = _rows(end, days=200, day_mult={14: .2})  # Nov 26 at 20%
        res = analyze.analyze(rows, end, self._cal_cfg())
        self.assertEqual(res["flags"], [], res["flags"])
        self.assertTrue(res["verdict"].startswith("Normal day"))

    def test_fixed_date_holiday_yoy_aligns_to_date_not_364_days(self):
        end = dt.date(2026, 7, 4)
        rows = _rows(end, days=400, day_mult={0: .6, 365: .6})  # July 4 both years at 60%
        res = analyze.analyze(rows, end, self._cal_cfg())
        self.assertEqual(res["yoy"]["ly_date"], "2025-07-04")
        self.assertEqual(res["yoy"]["aligned_by"], "holiday")
