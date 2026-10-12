"""Turn daily aggregate rows into findings.

Everything here is deterministic and warehouse-agnostic. Input is the row shape produced by
``review.query.build_query``: one row per (date, unit, channel[, extra dims]) with the measures
as columns. Output is a plain dict the brief renderer and the JSON file both consume.
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from typing import Any

from . import stats
from .context import Context
from .holidays import Calendar

Row = dict[str, Any]


def _f(x) -> float:
    return float(x or 0)


def _as_date(v) -> dt.date:
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, dt.date):
        return v
    return dt.date.fromisoformat(str(v)[:10])


class Cube:
    """Daily totals, sliced by unit / channel / extra dims. Just nested dicts of sums."""

    def __init__(self, rows: list[Row], measures: list[str], dims: list[str]):
        self.measures = measures
        self.dims = dims
        self.by_day: dict[dt.date, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        self.by_day_dim: dict[str, dict[dt.date, dict[str, dict[str, float]]]] = {
            d: defaultdict(lambda: defaultdict(lambda: defaultdict(float))) for d in dims
        }
        for r in rows:
            day = _as_date(r["d"])
            for m in measures:
                v = _f(r.get(m))
                self.by_day[day][m] += v
                for d in dims:
                    self.by_day_dim[d][day][str(r.get(d))][m] += v

    def total(self, day: dt.date, m: str) -> float:
        return self.by_day.get(day, {}).get(m, 0.0)

    def has(self, day: dt.date) -> bool:
        return day in self.by_day and self.by_day[day].get("revenue", 0) > 0

    def slice_total(self, dim: str, day: dt.date, key: str, m: str) -> float:
        return self.by_day_dim[dim].get(day, {}).get(key, {}).get(m, 0.0)

    def keys(self, dim: str, days: list[dt.date]) -> list[str]:
        ks: set[str] = set()
        for d in days:
            ks.update(self.by_day_dim[dim].get(d, {}).keys())
        return sorted(ks)


def _base_days(cube: Cube, day: dt.date, weeks: int, cal: Calendar) -> list[dt.date]:
    """Trailing same-weekday dates with data, skipping holidays (and their marked neighbours)."""
    return cal.clean_same_weekday(day, weeks, cube.has)


def _baseline_for(cube: Cube, day: dt.date, m: str, weeks: int, cal: Calendar) -> dict:
    return stats.robust_baseline([cube.total(d, m) for d in _base_days(cube, day, weeks, cal)])


def analyze(
    rows: list[Row],
    review_date: dt.date,
    cfg: dict,
    segment_rows: dict[str, list[Row]] | None = None,
    context_rows: list[dict] | None = None,
) -> dict:
    rules = cfg["rules"]
    weeks = int(rules.get("baseline_weeks", 8))
    z_thr = float(rules.get("z_threshold", 2.0))
    floor = float(rules.get("min_signal_revenue", 0))
    measures = [m for m in cfg["measures"].keys()]
    dims = ["unit", "channel"] + [d for d in cfg.get("extra_dimensions", {}) if any(d in r for r in rows[:1])]
    cube = Cube(rows, measures, dims)
    D = review_date
    cal = cfg.get("_calendar") or Calendar.load(cfg.get("holiday_calendar"), cfg.get("holidays"))
    hol = cal.lookup(D)  # (name, offset) or None
    ctx = Context(context_rows or [])

    out: dict[str, Any] = {
        "review_date": D.isoformat(),
        "weekday": D.strftime("%A"),
        "business": cfg["business"],
        "profile": cfg["profile"],
        "vocabulary": cfg["vocabulary"],
        "rules": rules,
        "flags": [],
        "warnings": [],
        "holiday": None,
    }
    if hol:
        name, off = hol
        label = name if off == 0 else (f"day before {name}" if off < 0 else f"day after {name}")
        out["holiday"] = {"name": name, "offset": off, "label": label, "is_anchor": off == 0}

    # ---- data presence -------------------------------------------------------------------
    if not cube.has(D):
        out["warnings"].append(
            f"No completed rows for {D.isoformat()}. Either the data has not landed yet or the "
            "business was closed. Nothing below should be trusted."
        )
        out["data_present"] = False
        return out
    out["data_present"] = True

    # ---- headline: today vs same-weekday baseline -------------------------------------------
    head = {}
    for m in measures:
        x = cube.total(D, m)
        base = _baseline_for(cube, D, m, weeks, cal)
        head[m] = {
            "value": x,
            "baseline": base["median"],
            "baseline_n": base["n"],
            "pct": stats.pct_change(x, base["median"]),
            "z": stats.zscore(x, base),
        }
    out["headline"] = head

    rev, orders = head["revenue"], head["orders"]
    if rev["baseline"] and orders["baseline"]:
        out["decomposition"] = stats.decompose(
            rev["value"], orders["value"], rev["baseline"], orders["baseline"]
        )
    if "sessions" in measures and head["sessions"]["value"]:
        s, o = head["sessions"], head["orders"]
        out["conversion"] = {
            "cvr": o["value"] / s["value"] if s["value"] else None,
            "base_cvr": (o["baseline"] / s["baseline"]) if s["baseline"] else None,
        }

    # ---- holiday: compare to the same holiday last year, not to normal weekdays ------------
    if hol:
        ly_h = cal.same_holiday_last_year(D)
        if ly_h and cube.has(ly_h):
            out["holiday"].update({
                "ly_date": ly_h.isoformat(),
                "ly_weekday": ly_h.strftime("%A"),
                "ly_revenue": cube.total(ly_h, "revenue"),
                "ly_orders": cube.total(ly_h, "orders"),
                "pct_vs_ly": stats.pct_change(rev["value"], cube.total(ly_h, "revenue")),
                "orders_pct_vs_ly": stats.pct_change(orders["value"], cube.total(ly_h, "orders")),
            })
        else:
            out["holiday"]["ly_date"] = ly_h.isoformat() if ly_h else None
            out["warnings"].append(f"{D.isoformat()} is {out['holiday']['label']} and there is no data for the same holiday last year, so the only comparison available is to normal {out['weekday']}s. Read the numbers with that in mind.")

    # ---- persistence: is today's move part of a run? ------------------------------------
    p_days = int(rules.get("persistence_days", 3))
    p_hits = int(rules.get("persistence_min_hits", 2))
    zs = []
    for k in range(p_days):
        d = D - dt.timedelta(days=k)
        if not cube.has(d):
            continue
        h = cal.lookup(d)
        zs.append({"date": d.isoformat(), "holiday": h[0] if h else None,
                   "z": None if h else stats.zscore(cube.total(d, "revenue"), _baseline_for(cube, d, "revenue", weeks, cal))})
    today_z = rev["z"] or 0.0
    sign = 1 if today_z > 0 else -1
    same_way = sum(1 for e in zs if e["z"] is not None and e["z"] * sign >= 1.0)
    persistent = (not hol) and abs(today_z) >= z_thr and same_way >= p_hits
    out["persistence"] = {"window": zs, "persistent": persistent, "min_hits": p_hits, "hits": same_way, "days": p_days,
                          "suspended": bool(hol)}

    # ---- week to date -------------------------------------------------------------------
    monday = D - dt.timedelta(days=D.weekday())
    wtd_days = [monday + dt.timedelta(days=i) for i in range((D - monday).days + 1)]
    wtd = sum(cube.total(d, "revenue") for d in wtd_days)
    lw = sum(cube.total(d - dt.timedelta(days=7), "revenue") for d in wtd_days)
    prior4 = [sum(cube.total(d - dt.timedelta(days=7 * k), "revenue") for d in wtd_days) for k in range(1, 5)]
    out["wtd"] = {
        "days": len(wtd_days),
        "revenue": wtd,
        "last_week_same_days": lw,
        "pct_vs_last_week": stats.pct_change(wtd, lw),
        "median_prior_4": stats.robust_baseline(prior4)["median"],
    }

    # ---- year over year (same weekday 52 weeks back) --------------------------------------
    ly = (cal.same_holiday_last_year(D) if hol else None) or (D - dt.timedelta(days=364))
    if cube.has(ly):
        t7 = sum(cube.total(D - dt.timedelta(days=i), "revenue") for i in range(7))
        ly7 = sum(cube.total(D - dt.timedelta(days=364 + i), "revenue") for i in range(7))
        out["yoy"] = {
            "ly_date": ly.isoformat(),
            "aligned_by": "holiday" if hol else "weekday",
            "day_pct": stats.pct_change(rev["value"], cube.total(ly, "revenue")),
            "trailing7_pct": stats.pct_change(t7, ly7),
        }
        ly_hol = cal.lookup(ly)
        if not hol and ly_hol:
            out["yoy"]["note"] = f"364 days back lands on {ly_hol[0]}, so the day comparison is not like-for-like."
        # holidays inside either 7-day window make the trailing-7 comparison unfair
        this7 = [cal.lookup(D - dt.timedelta(days=i)) for i in range(7)]
        last7 = [cal.lookup(D - dt.timedelta(days=364 + i)) for i in range(7)]
        if [bool(x) for x in this7] != [bool(x) for x in last7]:
            out["yoy"]["trailing7_note"] = "A holiday falls differently inside the two 7-day windows."

    # ---- weekly trend (complete weeks) -----------------------------------------------------
    trend_weeks = int(rules.get("trend_weeks", 13))
    last_complete_sunday = monday - dt.timedelta(days=1)
    trend = []
    for k in range(trend_weeks - 1, -1, -1):
        we = last_complete_sunday - dt.timedelta(days=7 * k)
        days = [we - dt.timedelta(days=i) for i in range(7)]
        ty = sum(cube.total(d, "revenue") for d in days)
        ly_days = [d - dt.timedelta(days=364) for d in days]
        ly_sum = sum(cube.total(d, "revenue") for d in ly_days) if all(cube.has(d) for d in ly_days) else None
        hols = sorted({cal.lookup(d)[0] for d in days if cal.is_anchor(d)})
        trend.append({"week_ending": we.isoformat(), "revenue": ty, "ly_revenue": ly_sum, "yoy_pct": stats.pct_change(ty, ly_sum), "holidays": hols})
    out["trend"] = trend

    # ---- unit movers --------------------------------------------------------------------
    move_pct = float(rules.get("unit_move_pct", 0.15))
    move_abs = float(rules.get("unit_move_abs", 500))
    movers = []
    base_days = _base_days(cube, D, weeks, cal)
    for u in cube.keys("unit", [D] + base_days):
        x = cube.slice_total("unit", D, u, "revenue")
        base = stats.robust_baseline([cube.slice_total("unit", d, u, "revenue") for d in base_days if cube.has(d)])
        if base["median"] is None:
            continue
        pct = stats.pct_change(x, base["median"])
        delta = x - base["median"]
        if pct is not None and abs(pct) >= move_pct and abs(delta) >= move_abs:
            # persistence at the unit level: did it move the same way yesterday?
            y = D - dt.timedelta(days=1)
            ybase = stats.robust_baseline([cube.slice_total("unit", d, u, "revenue") for d in _base_days(cube, y, weeks, cal)])
            ypct = stats.pct_change(cube.slice_total("unit", y, u, "revenue"), ybase["median"]) if (cube.has(y) and not cal.is_holiday(y)) else None
            movers.append({
                "unit": u, "revenue": x, "baseline": base["median"], "delta": delta, "pct": pct,
                "z": stats.zscore(x, base),
                "yesterday_pct": ypct,
                "persistent": ypct is not None and (ypct < 0) == (pct < 0) and abs(ypct) >= move_pct / 2,
            })
    movers.sort(key=lambda m: m["delta"])
    out["unit_movers"] = {"down": [m for m in movers if m["delta"] < 0][:5], "up": [m for m in reversed(movers) if m["delta"] > 0][:5], "total_units": len(cube.keys("unit", [D]))}

    # ---- mix shifts: channel (+ any extra dimension like daypart) ------------------------
    shift_pts = float(rules.get("channel_share_shift_pts", 2.0)) / 100.0
    out["mix"] = {}
    for dim in [d for d in dims if d != "unit"]:
        keys = cube.keys(dim, [D] + base_days)
        total_today = cube.total(D, "revenue")
        rows_out = []
        for k in keys:
            today = cube.slice_total(dim, D, k, "revenue")
            base_vals = [cube.slice_total(dim, d, k, "revenue") for d in base_days if cube.has(d)]
            base = stats.robust_baseline(base_vals)
            base_share_vals = [stats.share(cube.slice_total(dim, d, k, "revenue"), cube.total(d, "revenue")) for d in base_days if cube.has(d)]
            base_share = stats.robust_baseline([s for s in base_share_vals if s is not None])["median"]
            today_share = stats.share(today, total_today)
            rows_out.append({
                "key": k, "revenue": today, "baseline": base["median"], "pct": stats.pct_change(today, base["median"]),
                "share": today_share, "base_share": base_share,
                "share_shift": (today_share - base_share) if (today_share is not None and base_share is not None) else None,
            })
        rows_out.sort(key=lambda r: -(r["revenue"] or 0))
        out["mix"][dim] = {"rows": rows_out, "shifts": [r for r in rows_out if r["share_shift"] is not None and abs(r["share_shift"]) >= shift_pts]}

    # ---- excluded segments reported on their own ----------------------------------------
    out["segments"] = {}
    for name, srows in (segment_rows or {}).items():
        scube = Cube(srows, measures, ["unit"])
        x = scube.total(D, "revenue")
        base = _baseline_for(scube, D, "revenue", weeks, cal)
        out["segments"][name] = {"revenue": x, "baseline": base["median"], "pct": stats.pct_change(x, base["median"]), "z": stats.zscore(x, base)}

    # ---- context: what else was true that day ---------------------------------------------
    total_units = out["unit_movers"]["total_units"]
    out["context"] = {
        "today": [dict(r, date=r["date"].isoformat()) for r in ctx.on(D)],
        "yesterday": [dict(r, date=r["date"].isoformat()) for r in ctx.on(D - dt.timedelta(days=1))],
        "summary": ctx.summary(D, total_units, cfg["vocabulary"]),
        "weather_enabled": bool(cfg.get("weather", {}).get("enabled")),
    }
    for m in out["unit_movers"]["down"] + out["unit_movers"]["up"]:
        m["context"] = "; ".join(f"{r['kind']}: {r['note']}" if r["note"] else r["kind"] for r in ctx.on(D, m["unit"]))

    # ---- flags + verdict ----------------------------------------------------------------
    _flag(out, cfg, floor, z_thr)
    _attach_context(out, ctx, D)
    return out


def _attach_context(out: dict, ctx: Context, D: dt.date) -> None:
    """Hang context off the flags it explains. It never removes a flag."""
    summary = out["context"]["summary"]
    attached = False
    for f in out["flags"]:
        if f["kind"] in ("volume_drop", "value_drop", "up", "conversion_drop") and summary and not attached:
            f["context"] = summary
            attached = True
        elif f["kind"] == "channel_shift":
            # the channel that moved most is named in the flag text; attach rows for any channel
            ch_rows = [r for r in out["context"]["today"] if r["scope"].startswith("channel:")]
            if ch_rows:
                f["context"] = "; ".join(f"{r['scope'][8:]} {r['kind']}: {r['note']}" for r in ch_rows)
        elif f["kind"] == "unit_drop":
            bits = []
            for m in out["unit_movers"]["down"][:3]:
                if m.get("context"):
                    bits.append(f"{m['unit']}: {m['context']}")
            if bits:
                f["context"] = "; ".join(bits)
    if summary and out["flags"] and not out.get("holiday"):
        out["verdict"] += f" Context: {summary}."


def _flag(out: dict, cfg: dict, floor: float, z_thr: float) -> None:
    """Decide what is worth a human's attention. Order matters: the first flag drives the verdict."""
    pb = cfg["playbooks"]
    voc = cfg["vocabulary"]
    head = out["headline"]
    rev = head["revenue"]
    dec = out.get("decomposition") or {}
    flags = out["flags"]
    delta = (rev["value"] or 0) - (rev["baseline"] or 0)
    big_enough = abs(delta) >= floor
    moved = rev["z"] is not None and abs(rev["z"]) >= z_thr and big_enough

    hol = out.get("holiday")
    if hol and hol.get("is_anchor"):
        # A holiday is not a normal day. Compare to the same holiday last year and stop there:
        # every unit and channel will look wrong against weekday baselines, and that is not news.
        if hol.get("pct_vs_ly") is not None:
            flags.append({"kind": "holiday", "severity": "info",
                          "text": f"{hol['name']}: revenue {_pct(hol['pct_vs_ly'])} and {voc['orders']} {_pct(hol['orders_pct_vs_ly'])} vs {hol['name']} last year "
                                  f"({hol['ly_date']}, a {hol['ly_weekday']}). Weekday baselines are shown for reference only.",
                          "playbook": pb.get("general")})
            out["verdict"] = f"{hol['name']}: revenue {_pct(hol['pct_vs_ly'])} vs the same holiday last year."
        else:
            out["verdict"] = f"{hol['name']}: no same-holiday comparison available; {_pct(rev['pct'])} vs normal {out['weekday']}s, which is not a fair test."
        return
    if hol:
        flags.append({"kind": "holiday_adjacent", "severity": "info",
                      "text": f"Yesterday was the {hol['label']}. Baselines exclude past holidays, but expect the number to be off its weekday norm"
                              + (f"; vs the same day last year it is {_pct(hol['pct_vs_ly'])}." if hol.get("pct_vs_ly") is not None else "."),
                      "playbook": pb.get("general")})

    if moved and delta < 0:
        driver = "volume" if abs(dec.get("volume_effect", 0)) >= abs(dec.get("value_effect", 0)) else "value"
        if driver == "volume":
            flags.append({"kind": "volume_drop", "severity": "high" if out["persistence"]["persistent"] else "medium",
                          "text": f"Revenue is {_pct(rev['pct'])} vs the same-weekday baseline. Fewer {voc['orders']} cost {_money(dec['volume_effect'], cfg)}; "
                                  + (f"a higher {voc['value']} clawed back {_money(dec['value_effect'], cfg)}." if dec['value_effect'] > 0 else f"{voc['value']} took off another {_money(dec['value_effect'], cfg)}."),
                          "playbook": pb.get("volume_drop")})
        else:
            flags.append({"kind": "value_drop", "severity": "high" if out["persistence"]["persistent"] else "medium",
                          "text": f"Revenue is {_pct(rev['pct'])} vs baseline and the {voc['value']} is doing the damage "
                                  f"({_money(dec['value_effect'], cfg)} of the {_money(delta, cfg)} gap). {voc['orders'].capitalize()} "
                                  + ("held up." if abs(dec['volume_effect']) < floor else f"are also soft ({_money(dec['volume_effect'], cfg)})."),
                          "playbook": pb.get("value_drop")})
    elif not moved and head["orders"]["z"] is not None and head["orders"]["z"] <= -z_thr and big_enough_orders(head, floor, dec):
        flags.append({"kind": "volume_drop", "severity": "high" if out["persistence"]["persistent"] else "medium",
                      "text": f"{voc['orders'].capitalize()} are {_pct(head['orders']['pct'])} vs baseline (z {head['orders']['z']:+.1f}) and a higher {voc['value']} "
                              f"({_pct((dec['aov'] - dec['base_aov']) / dec['base_aov'] if dec.get('base_aov') else None)}) is hiding it in revenue. Treat this as a volume problem.",
                      "playbook": pb.get("volume_drop")})
    elif moved and delta > 0:
        flags.append({"kind": "up", "severity": "info",
                      "text": f"Revenue is {_pct(rev['pct'])} above the same-weekday baseline. Check whether a promotion, weather, or an event explains it before celebrating.",
                      "playbook": pb.get("general")})

    if out.get("conversion") and out["conversion"].get("base_cvr"):
        c = out["conversion"]
        if c["cvr"] is not None and stats.pct_change(c["cvr"], c["base_cvr"]) is not None and stats.pct_change(c["cvr"], c["base_cvr"]) <= -0.10:
            flags.append({"kind": "conversion_drop", "severity": "medium",
                          "text": f"Conversion is {_pct(stats.pct_change(c['cvr'], c['base_cvr']))} vs baseline on similar traffic.",
                          "playbook": pb.get("conversion_drop")})

    nc = head.get("new_customers")
    if nc and nc["z"] is not None and nc["z"] <= -z_thr and nc["baseline"] and (nc["baseline"] - nc["value"]) >= 10:
        flags.append({"kind": "new_customer_drop", "severity": "medium",
                      "text": f"New customers are {_pct(nc['pct'])} vs baseline ({int(nc['value'])} vs a typical {int(nc['baseline'])}).",
                      "playbook": pb.get("new_customer_drop")})

    down = out["unit_movers"]["down"]
    if down:
        worst = down[0]
        if worst["persistent"] or len(down) >= 3:
            names = ", ".join(m["unit"] for m in down[:3])
            noun = voc['unit'] if len(down) == 1 else voc['units']
            verb = "is" if len(down) == 1 else "are"
            flags.append({"kind": "unit_drop", "severity": "high" if worst["persistent"] else "medium",
                          "text": f"{len(down)} {noun} {verb} off by {int(cfg['rules'].get('unit_move_pct', .15) * 100)}%+ vs {'its' if len(down) == 1 else 'their'} own baseline ({names}). "
                                  + (f"{worst['unit']} was down yesterday too." if worst["persistent"] else "None of them was down yesterday, so watch before acting."),
                          "playbook": pb.get("unit_drop")})

    for dim, mix in out["mix"].items():
        if mix["shifts"]:
            s = sorted(mix["shifts"], key=lambda r: -abs(r["share_shift"]))[0]
            kind = "channel_shift" if dim == "channel" else f"{dim}_shift"
            flags.append({"kind": kind, "severity": "low",
                          "text": f"{dim.capitalize()} mix moved: {s['key']} is {s['share_shift']*100:+.1f} pts of revenue share vs its usual {s['base_share']*100:.0f}%.",
                          "playbook": pb.get(kind, pb.get("general"))})

    # Verdict: one sentence a CEO can read without the rest.
    if out["persistence"]["persistent"] and delta < 0:
        p = out["persistence"]
        verdict = f"Soft, and it is a trend: revenue {_pct(rev['pct'])} vs baseline today, and below baseline on {p['hits']} of the last {p['days']} days."
    elif moved and delta < 0:
        verdict = f"Soft day: revenue {_pct(rev['pct'])} vs the same-weekday baseline, but a one-off so far."
    elif moved and delta > 0:
        verdict = f"Strong day: revenue {_pct(rev['pct'])} vs baseline."
    else:
        verdict = f"Normal day: revenue {_pct(rev['pct'])} vs the same-weekday baseline, inside the usual range."
        if down and down[0]["persistent"]:
            verdict += f" The thing to look at is {down[0]['unit']}."
    out["verdict"] = verdict


def big_enough_orders(head: dict, floor: float, dec: dict) -> bool:
    """A volume drop counts when the orders it cost would have been worth at least the floor."""
    return abs(dec.get("volume_effect", 0)) >= floor


def _pct(p: float | None) -> str:
    return "n/a" if p is None else f"{p*100:+.1f}%"


def _money(x: float, cfg: dict) -> str:
    cur = cfg["business"].get("currency", "USD")
    sym = {"USD": "$", "CAD": "C$", "GBP": "£", "EUR": "€"}.get(cur, cur + " ")
    return f"{'-' if x < 0 else ''}{sym}{abs(x):,.0f}"
