"""Holiday calendar: which dates are not comparable to a normal weekday.

Holidays are expressed as rules so the calendar works for any year:

    - name: Thanksgiving
      rule: nth_weekday            # the Nth <weekday> of <month>
      month: 11
      weekday: 3                   # Monday = 0
      n: 4                         # negative counts from the end (-1 = last)
      around: [-1, 1]              # also mark the day before and the day after

    - name: Independence Day
      rule: fixed
      month: 7
      day: 4
      observed: true               # if it lands on a weekend, the observed weekday also counts

    - name: Easter
      rule: easter                 # Western Easter; `offset` days from it (-2 = Good Friday)
      offset: 0

Each holiday rule produces one "anchor" date per year plus optional neighbours. The engine
drops all of these dates from same-weekday baselines, and compares a holiday review day to
the same holiday last year instead of to normal weekdays.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CALENDAR = ROOT / "profiles" / "holidays.yaml"


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> dt.date:
    if n > 0:
        first = dt.date(year, month, 1)
        offset = (weekday - first.weekday()) % 7
        return first + dt.timedelta(days=offset + 7 * (n - 1))
    # count from the end of the month
    nxt = dt.date(year + (month == 12), (month % 12) + 1, 1)
    last = nxt - dt.timedelta(days=1)
    offset = (last.weekday() - weekday) % 7
    return last - dt.timedelta(days=offset + 7 * (-n - 1))


def _easter(year: int) -> dt.date:
    """Anonymous Gregorian algorithm."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = (h + l - 7 * m + 114) % 31 + 1
    return dt.date(year, month, day)


class Calendar:
    def __init__(self, rules: list[dict]):
        self.rules = rules or []
        self._cache: dict[int, dict[dt.date, tuple[str, int]]] = {}

    @classmethod
    def load(cls, path: str | Path | None = None, extra: list[dict] | None = None) -> "Calendar":
        rules: list[dict] = []
        p = Path(path) if path else DEFAULT_CALENDAR
        if p.exists():
            rules += (yaml.safe_load(p.read_text()) or {}).get("holidays", []) or []
        rules += extra or []
        return cls(rules)

    def anchor(self, rule: dict, year: int) -> dt.date | None:
        kind = rule.get("rule", "fixed")
        try:
            if kind == "fixed":
                return dt.date(year, int(rule["month"]), int(rule["day"]))
            if kind == "nth_weekday":
                return _nth_weekday(year, int(rule["month"]), int(rule["weekday"]), int(rule["n"]))
            if kind == "easter":
                return _easter(year) + dt.timedelta(days=int(rule.get("offset", 0)))
        except (KeyError, ValueError):
            return None
        return None

    def _year(self, year: int) -> dict[dt.date, tuple[str, int]]:
        """date -> (holiday name, offset from the anchor). Offset 0 is the holiday itself."""
        if year in self._cache:
            return self._cache[year]
        out: dict[dt.date, tuple[str, int]] = {}
        for rule in self.rules:
            a = self.anchor(rule, year)
            if not a:
                continue
            name = rule.get("name", "holiday")
            out.setdefault(a, (name, 0))
            if rule.get("observed") and a.weekday() >= 5:
                obs = a + dt.timedelta(days=1 if a.weekday() == 6 else -1)
                out.setdefault(obs, (name + " (observed)", 0))
            for off in rule.get("around", []) or []:
                d = a + dt.timedelta(days=int(off))
                out.setdefault(d, (name, int(off)))
        self._cache[year] = out
        return out

    def lookup(self, day: dt.date) -> tuple[str, int] | None:
        """(name, offset) if the day is a holiday or a marked neighbour, else None."""
        hit = self._year(day.year).get(day)
        if hit:
            return hit
        # a neighbour of a late-December holiday can spill into the next year
        return self._year(day.year - 1).get(day) or self._year(day.year + 1).get(day)

    def is_holiday(self, day: dt.date) -> bool:
        return self.lookup(day) is not None

    def is_anchor(self, day: dt.date) -> bool:
        hit = self.lookup(day)
        return bool(hit and hit[1] == 0)

    def same_holiday_last_year(self, day: dt.date) -> dt.date | None:
        """The date that played the same role last year: the same holiday, same offset."""
        hit = self.lookup(day)
        if not hit:
            return None
        name, off = hit
        base_name = name.replace(" (observed)", "")
        for rule in self.rules:
            if rule.get("name") == base_name:
                a = self.anchor(rule, day.year - 1)
                if a:
                    if name.endswith("(observed)") and rule.get("observed") and a.weekday() >= 5:
                        a = a + dt.timedelta(days=1 if a.weekday() == 6 else -1)
                    return a + dt.timedelta(days=off)
        return None

    def clean_same_weekday(self, day: dt.date, weeks: int, has_data, max_reach: int = 20) -> list[dt.date]:
        """Trailing same-weekday dates that are neither holidays nor missing, reaching back up to
        ``max_reach`` weeks to collect ``weeks`` clean observations."""
        out = []
        for k in range(1, max_reach + 1):
            d = day - dt.timedelta(days=7 * k)
            if self.is_holiday(d) or not has_data(d):
                continue
            out.append(d)
            if len(out) == weeks:
                break
        return out
