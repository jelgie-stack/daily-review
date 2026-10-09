"""The small amount of statistics the method needs. No numpy, no pandas: stdlib only."""

from __future__ import annotations

import datetime as dt
import statistics
from typing import Iterable

MAD_SCALE = 1.4826  # makes MAD comparable to a standard deviation for normal data


def same_weekday_dates(day: dt.date, weeks: int) -> list[dt.date]:
    """The trailing ``weeks`` occurrences of ``day``'s weekday, most recent first, excluding day."""
    return [day - dt.timedelta(days=7 * k) for k in range(1, weeks + 1)]


def robust_baseline(values: Iterable[float]) -> dict:
    """Median and a robust spread (scaled MAD, falling back to stdev when MAD is 0)."""
    vals = [float(v) for v in values if v is not None]
    if not vals:
        return {"n": 0, "median": None, "spread": None}
    med = statistics.median(vals)
    mad = statistics.median(abs(v - med) for v in vals)
    spread = MAD_SCALE * mad
    if spread == 0 and len(vals) > 1:
        spread = statistics.pstdev(vals)
    return {"n": len(vals), "median": med, "spread": spread}


def zscore(x: float | None, base: dict) -> float | None:
    if x is None or base.get("median") is None:
        return None
    spread = base.get("spread") or 0.0
    if spread == 0:
        return 0.0 if x == base["median"] else (3.0 if x > base["median"] else -3.0)
    return (x - base["median"]) / spread


def pct_change(x: float | None, base: float | None) -> float | None:
    if x is None or base in (None, 0):
        return None
    return (x - base) / base


def decompose(revenue: float, orders: float, base_revenue: float, base_orders: float) -> dict:
    """Split revenue - base_revenue into a volume effect and a value (AOV) effect.

    volume_effect = (orders - base_orders) * base_aov
    value_effect  = orders * (aov - base_aov)
    The two sum exactly to the revenue delta.
    """
    aov = revenue / orders if orders else 0.0
    base_aov = base_revenue / base_orders if base_orders else 0.0
    volume_effect = (orders - base_orders) * base_aov
    value_effect = orders * (aov - base_aov)
    return {
        "delta": revenue - base_revenue,
        "aov": aov,
        "base_aov": base_aov,
        "volume_effect": volume_effect,
        "value_effect": value_effect,
    }


def share(part: float, whole: float) -> float | None:
    return part / whole if whole else None
