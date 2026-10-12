"""Render findings as the morning brief (Markdown). Written for a reader with two minutes."""

from __future__ import annotations

import datetime as dt


def _pct(p):
    return "n/a" if p is None else f"{p*100:+.1f}%"


def _n(x):
    return "n/a" if x is None else f"{x:,.0f}"


def _money(x, cur="USD"):
    if x is None:
        return "n/a"
    sym = {"USD": "$", "CAD": "C$", "GBP": "£", "EUR": "€"}.get(cur, cur + " ")
    return f"{'-' if x < 0 else ''}{sym}{abs(x):,.0f}"


def _bar(pct, width=12):
    """Tiny text sparkline for the trend table."""
    if pct is None:
        return ""
    n = max(-width, min(width, int(round(pct * 100 / 2))))  # 2 pts per block
    return ("▇" * n) if n > 0 else ("▁" * (-n))


def render(res: dict) -> str:
    cur = res["business"].get("currency", "USD")
    voc = res["vocabulary"]
    day = dt.date.fromisoformat(res["review_date"])
    lines = []
    lines.append(f"# {res['business'].get('name', 'Daily review')}: {res['weekday']} {day.strftime('%b %-d, %Y')}")
    lines.append("")

    if not res.get("data_present"):
        lines.append("> **No data.** " + " ".join(res["warnings"]))
        return "\n".join(lines) + "\n"

    hol = res.get("holiday")
    if hol:
        lines.append(f"_Calendar: {hol['label']}._")
        lines.append("")
    lines.append(f"**{res['verdict']}**")
    lines.append("")

    # ---- flags
    if res["flags"]:
        lines.append("## What needs attention")
        lines.append("")
        for f in res["flags"]:
            sev = {"high": "🔴", "medium": "🟠", "low": "🟡", "info": "🟢"}.get(f["severity"], "•")
            pb = f" _Playbook: `{f['playbook']}`_" if f.get("playbook") else ""
            lines.append(f"- {sev} {f['text']}{pb}")
            if f.get("context"):
                lines.append(f"  - _Context: {f['context']}._")
        lines.append("")
    else:
        lines.append("## What needs attention")
        lines.append("")
        lines.append("- Nothing. Every measure is inside its usual same-weekday range.")
        lines.append("")

    # ---- headline table
    h = res["headline"]
    lines.append("## Yesterday vs. the same weekday")
    lines.append("")
    lines.append(f"Baseline = median of the trailing {h['revenue']['baseline_n']} {res['weekday']}s, skipping holidays. z = robust z-score; |z| ≥ {res['rules'].get('z_threshold', 2)} counts as a real move.")
    lines.append("")
    lines.append("| Measure | Yesterday | Baseline | Change | z |")
    lines.append("|---|---:|---:|---:|---:|")
    for m, v in h.items():
        label = {"revenue": "Revenue", "orders": voc["orders"].capitalize(), "new_customers": "New customers", "sessions": "Sessions", "units_sold": "Units sold"}.get(m, m)
        fmt = _money if m == "revenue" else _n
        val = fmt(v["value"], cur) if m == "revenue" else fmt(v["value"])
        base = fmt(v["baseline"], cur) if m == "revenue" else fmt(v["baseline"])
        z = "" if v["z"] is None else f"{v['z']:+.1f}"
        lines.append(f"| {label} | {val} | {base} | {_pct(v['pct'])} | {z} |")
    dec = res.get("decomposition")
    if dec:
        lines.append(f"| {voc['value_short']} | {_money(dec['aov'], cur)} | {_money(dec['base_aov'], cur)} | {_pct((dec['aov'] - dec['base_aov']) / dec['base_aov'] if dec['base_aov'] else None)} | |")
    if res.get("conversion") and res["conversion"].get("cvr") is not None:
        c = res["conversion"]
        lines.append(f"| Conversion | {c['cvr']*100:.2f}% | {c['base_cvr']*100:.2f}% | {_pct((c['cvr']-c['base_cvr'])/c['base_cvr'] if c['base_cvr'] else None)} | |")
    lines.append("")
    if dec:
        lines.append(f"**Why:** of the {_money(dec['delta'], cur)} gap to baseline, {_money(dec['volume_effect'], cur)} is {voc['orders']} (volume) and {_money(dec['value_effect'], cur)} is {voc['value']} (value).")
        lines.append("")

    # ---- persistence, wtd, yoy
    p = res["persistence"]
    zs = ", ".join((f"{e['date'][5:]}: {e['z']:+.1f}" if e["z"] is not None else f"{e['date'][5:]}: {e.get('holiday') or 'n/a'}") for e in p["window"])
    if p.get("suspended"):
        lines.append(f"**Run check:** suspended on a holiday ({zs}). A holiday never starts or extends a trend.")
    else:
        lines.append(f"**Run check:** revenue z over the last {p['days']} days ({zs}). " + ("Same direction on enough days to call it a trend." if p["persistent"] else "Not enough days pointing the same way to call it a trend."))
    lines.append("")
    w = res["wtd"]
    lines.append(f"**Week to date ({w['days']} day{'s' if w['days'] != 1 else ''}):** {_money(w['revenue'], cur)}, {_pct(w['pct_vs_last_week'])} vs the same days last week; typical for these days is {_money(w['median_prior_4'], cur)}.")
    if res.get("yoy"):
        y = res["yoy"]
        how = "the same holiday last year" if y.get("aligned_by") == "holiday" else "the same weekday last year"
        notes = " ".join(n for n in (y.get("note"), y.get("trailing7_note")) if n)
        lines.append(f"**Year over year:** {_pct(y['day_pct'])} vs {how} ({y['ly_date']}); trailing 7 days {_pct(y['trailing7_pct'])}." + (f" _{notes}_" if notes else ""))
    lines.append("")

    # ---- units
    um = res["unit_movers"]
    lines.append(f"## {voc['units'].capitalize()} that moved ({um['total_units']} reporting)")
    lines.append("")
    if not um["down"] and not um["up"]:
        lines.append(f"No {voc['unit']} moved more than {int(res['rules'].get('unit_move_pct', .15)*100)}% against its own baseline.")
    else:
        lines.append(f"| {voc['unit'].capitalize()} | Yesterday | Baseline | Change | Yesterday too? | Context |")
        lines.append("|---|---:|---:|---:|:---:|---|")
        for m in um["down"] + um["up"]:
            yt = "yes" if m["persistent"] else ("no" if m["yesterday_pct"] is not None else "")
            lines.append(f"| {m['unit']} | {_money(m['revenue'], cur)} | {_money(m['baseline'], cur)} | {_pct(m['pct'])} | {yt} | {m.get('context') or ''} |")
    lines.append("")

    # ---- mix
    for dim, mix in res["mix"].items():
        lines.append(f"## {dim.capitalize()} mix")
        lines.append("")
        lines.append(f"| {dim.capitalize()} | Revenue | vs baseline | Share | Usual share |")
        lines.append("|---|---:|---:|---:|---:|")
        for r in mix["rows"]:
            sh = "" if r["share"] is None else f"{r['share']*100:.0f}%"
            bs = "" if r["base_share"] is None else f"{r['base_share']*100:.0f}%"
            lines.append(f"| {r['key']} | {_money(r['revenue'], cur)} | {_pct(r['pct'])} | {sh} | {bs} |")
        lines.append("")

    # ---- segments
    if res.get("segments"):
        lines.append("## Reported separately")
        lines.append("")
        for name, s in res["segments"].items():
            lines.append(f"- **{name.capitalize()}:** {_money(s['revenue'], cur)} vs a typical {_money(s['baseline'], cur)} ({_pct(s['pct'])}). Kept out of the core numbers above.")
        lines.append("")

    # ---- context
    c = res.get("context") or {}
    if c.get("today") or c.get("yesterday"):
        lines.append("## Context")
        lines.append("")
        lines.append("What else was true. Context explains flags; it never hides them.")
        lines.append("")
        for label, rows_ in (("Yesterday", c.get("today") or []), ("The day before", c.get("yesterday") or [])):
            wx = [r for r in rows_ if r["kind"] == "weather"]
            other = [r for r in rows_ if r["kind"] != "weather"]
            for r in other:
                scope = "" if r["scope"] == "all" else f" ({r['scope']})"
                lines.append(f"- **{label}{scope}, {r['kind']}:** {r['note']}")
            if wx:
                lines.append(f"- **{label}, weather:** " + "; ".join(f"{r['scope']} {r['note']}" for r in wx[:8]) + (f"; +{len(wx)-8} more" if len(wx) > 8 else ""))
        lines.append("")
    elif c.get("weather_enabled"):
        lines.append("## Context")
        lines.append("")
        lines.append("Nothing logged and no notable weather at any unit.")
        lines.append("")

    # ---- trend
    lines.append(f"## {len(res['trend'])}-week trend (complete weeks)")
    lines.append("")
    has_ly = any(t["ly_revenue"] for t in res["trend"])
    lines.append("| Week ending | Revenue | YoY |  | Holidays |" if has_ly else "| Week ending | Revenue | Holidays |")
    lines.append("|---|---:|---:|---|---|" if has_ly else "|---|---:|---|")
    for t in res["trend"]:
        hs = ", ".join(t.get("holidays") or [])
        if has_ly:
            lines.append(f"| {t['week_ending']} | {_money(t['revenue'], cur)} | {_pct(t['yoy_pct'])} | {_bar(t['yoy_pct'])} | {hs} |")
        else:
            lines.append(f"| {t['week_ending']} | {_money(t['revenue'], cur)} | {hs} |")
    lines.append("")

    if res["warnings"]:
        lines.append("## Warnings")
        lines.append("")
        for wmsg in res["warnings"]:
            lines.append(f"- {wmsg}")
        lines.append("")

    lines.append("---")
    lines.append(f"_Generated by daily-review · profile `{res['profile']}` · rules: baseline {res['rules'].get('baseline_weeks', 8)} weeks, z ≥ {res['rules'].get('z_threshold', 2)}, floor {_money(res['rules'].get('min_signal_revenue', 0), cur)}_")
    return "\n".join(lines) + "\n"
