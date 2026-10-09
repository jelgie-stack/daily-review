"""CLI entry point.

    python -m review.run --config config/config.yaml [--date 2026-10-08] [--print-sql] [--json]

Pulls the window the method needs (53 weeks so the YoY and 13-week trend have data), runs the
analysis, and writes the brief to <output.dir>/YYYYMMDD-daily-review.md plus a JSON twin.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

from adapters import get_adapter

from . import analyze, brief, query
from .config import load_config

LOOKBACK_DAYS = 371  # 53 weeks: enough for a 13-week trend with a YoY comparison


def _parse_date(s: str | None, tz: str | None) -> dt.date:
    if s:
        return dt.date.fromisoformat(s)
    # Default: yesterday in the business time zone (the review runs in the morning).
    try:
        from zoneinfo import ZoneInfo

        now = dt.datetime.now(ZoneInfo(tz)) if tz else dt.datetime.now()
    except Exception:
        now = dt.datetime.now()
    return (now - dt.timedelta(days=1)).date()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Run the daily review.")
    ap.add_argument("--config", required=True, help="path to config.yaml")
    ap.add_argument("--date", help="review date (YYYY-MM-DD). Default: yesterday in the business time zone")
    ap.add_argument("--print-sql", action="store_true", help="print the query and exit (run it elsewhere)")
    ap.add_argument("--json", action="store_true", help="also print the findings JSON to stdout")
    ap.add_argument("--rows", help="skip the warehouse: load rows from a JSON or CSV file produced by the printed SQL")
    args = ap.parse_args(argv)

    cfg = load_config(args.config)
    review_date = _parse_date(args.date, cfg["business"].get("timezone"))
    start = review_date - dt.timedelta(days=LOOKBACK_DAYS)

    core_sql = query.build_query(cfg, start, review_date)
    seg_sql = {s["name"]: query.build_query(cfg, start, review_date, segment=s["name"]) for s in query.available_segments(cfg)}

    if args.print_sql:
        print("-- core\n" + core_sql + ";\n")
        for name, sql in seg_sql.items():
            print(f"-- segment: {name}\n{sql};\n")
        return 0

    if args.rows:
        rows = _load_rows(args.rows)
        seg_rows = {}
    else:
        adapter = get_adapter(cfg)
        rows = adapter.run(core_sql)
        seg_rows = {name: adapter.run(sql) for name, sql in seg_sql.items()}

    if not rows:
        print("The core query returned no rows. Check config.source and the date column.", file=sys.stderr)
        return 2

    res = analyze.analyze(rows, review_date, cfg, seg_rows)
    md = brief.render(res)

    out_dir = Path(cfg["output"].get("dir", "out"))
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = review_date.strftime("%Y%m%d") + "-daily-review"
    (out_dir / f"{stem}.md").write_text(md)
    (out_dir / f"{stem}.json").write_text(json.dumps(res, indent=2, default=str))

    print(md)
    if args.json:
        print(json.dumps(res, indent=2, default=str))
    print(f"[written] {out_dir / (stem + '.md')}", file=sys.stderr)
    return 0


def _load_rows(path: str) -> list[dict]:
    p = Path(path)
    if p.suffix.lower() == ".json":
        return json.loads(p.read_text())
    import csv

    with p.open() as f:
        return list(csv.DictReader(f))


if __name__ == "__main__":
    sys.exit(main())
