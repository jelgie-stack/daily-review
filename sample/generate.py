"""Build a fake business so the review can be run with no warehouse.

    python sample/generate.py [--end 2026-10-08] [--units 12] [--seed 7]

Writes sample/sample.duckdb with one table, ``orders``, at order grain:

    order_id, order_ts, unit_id, channel, net_sales, customer_order_number,
    is_catering, order_status

Several anomalies are planted on the last day (``--end``) so the review has something to find:

  * overall volume is soft on the last two days (orders -9% then -5%), AOV slightly up
  * unit U07 is down ~35% on both days (a persistent, store-level problem)
  * unit U04 is down ~20% on the last day only (a one-off)
  * delivery takes ~4 pts of revenue share from in-store on the last day
  * the share of first-time customers drops from ~25% to ~18% on the last day
  * holidays behave like holidays: Thanksgiving and Christmas Day at ~15% of normal, Christmas
    Eve and July 4 at ~60%, Mother's Day at ~150%, so the calendar logic has something to chew on

Nothing here is real: the brand, units, prices and customers are all invented.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import math
import random
from pathlib import Path

HERE = Path(__file__).resolve().parent

CHANNELS = [("in-store", 0.62, 14.0), ("online", 0.24, 17.5), ("delivery", 0.14, 21.0)]  # name, share, avg ticket
WEEKDAY = {0: 0.86, 1: 0.90, 2: 0.94, 3: 1.00, 4: 1.18, 5: 1.22, 6: 0.90}  # Mon..Sun
HOUR_W = {7: 1, 8: 2, 9: 2, 10: 3, 11: 9, 12: 14, 13: 10, 14: 4, 15: 3, 16: 4, 17: 9, 18: 12, 19: 9, 20: 5, 21: 2}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--end", default="2026-10-08", help="last day of data (the review date)")
    ap.add_argument("--days", type=int, default=430)
    ap.add_argument("--units", type=int, default=12)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", default=str(HERE / "sample.duckdb"))
    args = ap.parse_args()

    rng = random.Random(args.seed)
    end = dt.date.fromisoformat(args.end)
    start = end - dt.timedelta(days=args.days - 1)
    units = [f"U{i:02d}" for i in range(1, args.units + 1)]
    unit_size = {u: rng.uniform(0.7, 1.4) for u in units}
    hours = list(HOUR_W.keys())
    hour_w = list(HOUR_W.values())
    chan_names = [c[0] for c in CHANNELS]

    csv_path = HERE / "orders.csv"
    n = 0
    with csv_path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["order_id", "order_ts", "unit_id", "channel", "net_sales", "customer_order_number", "is_catering", "order_status"])
        day = start
        while day <= end:
            days_from_end = (end - day).days
            # gentle growth + mild annual seasonality
            yearly = 1 + 0.04 * (1 - days_from_end / args.days) + 0.05 * math.sin(2 * math.pi * day.timetuple().tm_yday / 365)
            base = 80 * WEEKDAY[day.weekday()] * yearly

            # holiday effects (US), so the calendar has something to work on
            hol_mult = 1.0
            if (day.month, day.day) in ((11, 26), (12, 25)) and day.year == 2026 or (day.month, day.day) in ((11, 27), (12, 25)) and day.year == 2025:
                hol_mult = 0.15          # Thanksgiving (4th Thu: Nov 27 2025, Nov 26 2026) and Christmas Day
            elif (day.month, day.day) in ((12, 24), (7, 4), (1, 1)):
                hol_mult = 0.6
            elif day.month == 5 and day.weekday() == 6 and 8 <= day.day <= 14:
                hol_mult = 1.5           # Mother's Day
            base *= hol_mult

            # planted top-line softness on the last two days
            vol_mult = {0: 0.91, 1: 0.95}.get(days_from_end, 1.0)
            aov_mult = {0: 1.03}.get(days_from_end, 1.0)
            new_share = 0.18 if days_from_end == 0 else 0.25
            chan_w = [0.58, 0.24, 0.18] if days_from_end == 0 else [c[1] for c in CHANNELS]

            for u in units:
                unit_mult = 1.0
                if u == "U07" and days_from_end in (0, 1):
                    unit_mult = 0.6
                if u == "U04" and days_from_end == 0:
                    unit_mult = 0.80
                lam = base * unit_size[u] * vol_mult * unit_mult
                k = max(0, int(rng.gauss(lam, lam * 0.08)))
                for _ in range(k):
                    hr = rng.choices(hours, hour_w)[0]
                    ts = dt.datetime.combine(day, dt.time(hr, rng.randrange(60), rng.randrange(60)))
                    ch_i = rng.choices(range(3), chan_w)[0]
                    ticket = max(4.0, rng.gauss(CHANNELS[ch_i][2], 5.5)) * aov_mult
                    catering = rng.random() < 0.004
                    if catering:
                        ticket = rng.uniform(90, 320)
                    con = 1 if rng.random() < new_share else rng.randint(2, 40)
                    status = "completed" if rng.random() > 0.02 else "cancelled"
                    n += 1
                    w.writerow([f"o{n:08d}", ts.isoformat(sep=" "), u, chan_names[ch_i], f"{ticket:.2f}", con, "true" if catering else "false", status])
            day += dt.timedelta(days=1)

    import duckdb

    out = Path(args.out)
    if out.exists():
        out.unlink()
    con = duckdb.connect(str(out))
    con.execute("CREATE TABLE orders AS SELECT * FROM read_csv_auto(?, header=true)", [str(csv_path)])
    cnt = con.execute("SELECT COUNT(*), MIN(order_ts), MAX(order_ts) FROM orders").fetchone()
    con.close()
    csv_path.unlink()
    print(f"wrote {out} with {cnt[0]:,} orders from {cnt[1]} to {cnt[2]}")


if __name__ == "__main__":
    main()
