"""Build the one ANSI-SQL query the engine needs.

The warehouse does the GROUP BY; Python does everything else. Keeping the SQL this simple is
what makes the review portable: BigQuery, Snowflake, Postgres, Redshift and DuckDB all accept
``CAST(x AS DATE)``, ``DATE 'yyyy-mm-dd'`` literals and ordinal GROUP BYs.
"""

from __future__ import annotations

import datetime as dt
from typing import Any


def _extra_dims(cfg: dict) -> dict[str, str]:
    """Resolve profile extra dimensions (e.g. daypart) to SQL expressions."""
    dims: dict[str, str] = {}
    cols = cfg["columns"]
    for name, spec in cfg.get("extra_dimensions", {}).items():
        expr = cols.get(name)
        if not expr and spec.get("default_expr"):
            if "{hour}" in spec["default_expr"]:
                if not cols.get("hour"):
                    continue  # can't derive it; skip the dimension silently
                expr = spec["default_expr"].replace("{hour}", cols["hour"])
            else:
                expr = spec["default_expr"]
        if expr:
            dims[name] = " ".join(expr.split())
    return dims


def build_query(
    cfg: dict,
    start: dt.date,
    end: dt.date,
    segment: str | None = None,
    exclude_segments: bool = True,
) -> str:
    """Return the daily aggregate query for [start, end].

    ``segment``: restrict to one named segment (its filter predicate must be in config.filters).
    ``exclude_segments``: when True, segments the profile marks exclude_from_core are removed.
    """
    cols = cfg["columns"]
    measures = cfg["measures"]
    extra = _extra_dims(cfg)

    channel_expr = cols.get("channel") or "'all'"
    select = [
        f"CAST({cols['date']} AS DATE) AS d",
        f"{cols['unit']} AS unit",
        f"{channel_expr} AS channel",
    ]
    for name, expr in extra.items():
        select.append(f"{expr} AS {name}")
    group_n = len(select)
    for name, expr in measures.items():
        select.append(f"{expr} AS {name}")

    where = [
        f"CAST({cols['date']} AS DATE) BETWEEN DATE '{start.isoformat()}' AND DATE '{end.isoformat()}'"
    ]
    where += [f"({p})" for p in cfg["filters"].get("core", []) or []]

    seg_specs = cfg.get("segments", {}).get("exclude_from_core", []) or []
    if segment:
        spec = next((s for s in seg_specs if s["name"] == segment), None)
        pred = cfg["filters"].get(spec["filter_key"]) if spec else None
        if not pred:
            raise ValueError(f"Segment '{segment}' has no filter predicate in config.filters")
        where.append(f"({pred})")
    elif exclude_segments:
        for spec in seg_specs:
            pred = cfg["filters"].get(spec["filter_key"])
            if pred:
                where.append(f"NOT ({pred})")

    sql = (
        "SELECT\n  " + ",\n  ".join(select)
        + f"\nFROM {cfg['source']}"
        + "\nWHERE " + "\n  AND ".join(where)
        + "\nGROUP BY " + ", ".join(str(i + 1) for i in range(group_n))
        + "\nORDER BY 1, 2, 3"
    )
    return sql


def available_segments(cfg: dict) -> list[dict[str, Any]]:
    out = []
    for spec in cfg.get("segments", {}).get("exclude_from_core", []) or []:
        if cfg["filters"].get(spec["filter_key"]):
            out.append(spec)
    return out


def extra_dimension_names(cfg: dict) -> list[str]:
    return list(_extra_dims(cfg).keys())
