"""Context: things that explain a day but are not in the sales data.

A context row is (date, scope, kind, note[, severity, source]). Scope is ``all``, a unit id,
or ``channel:<name>``. Kinds are free text; ``promo``, ``outage``, ``hours``, ``event``,
``weather``, ``competitor``, ``pricing`` are the ones the brief knows how to phrase.

Rows come from three places:

1. ``context.rows`` in config and/or ``context.file`` (CSV with columns
   date,scope,kind,note[,severity,source]). This is where internal events live: a promo
   ending, an app outage, reduced hours. Someone has to write them down; nothing else can.
2. The weather provider (opt-in): one row per unit per notable-weather day, from Open-Meteo
   or from a CSV for offline use.
3. An agent appending rows to the CSV from what it finds in email or chat (see SKILL.md).

Context never suppresses a flag. It attaches to it. A rainy day with a real problem under
it is exactly the day a human needs to see both.
"""

from __future__ import annotations

import csv
import datetime as dt
import json
from pathlib import Path
from typing import Any

Row = dict[str, Any]


def _as_date(v) -> dt.date:
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, dt.date):
        return v
    return dt.date.fromisoformat(str(v)[:10])


def _norm(r: dict) -> Row | None:
    try:
        d = _as_date(r["date"])
    except Exception:
        return None
    return {
        "date": d,
        "scope": str(r.get("scope") or "all").strip(),
        "kind": str(r.get("kind") or "note").strip().lower(),
        "note": str(r.get("note") or "").strip(),
        "severity": str(r.get("severity") or "").strip().lower() or None,
        "source": str(r.get("source") or "manual").strip(),
    }


def load_manual(cfg: dict, base_dir: Path) -> list[Row]:
    ctx = cfg.get("context") or {}
    rows: list[Row] = []
    for r in ctx.get("rows") or []:
        n = _norm(r)
        if n:
            rows.append(n)
    f = ctx.get("file")
    if f:
        p = Path(f)
        if not p.is_absolute():
            p = base_dir / p
        if p.exists():
            with p.open() as fh:
                for r in csv.DictReader(fh):
                    n = _norm(r)
                    if n:
                        rows.append(n)
    return rows


# ---------------------------------------------------------------- weather ----------------

# Daily thresholds for "notable" weather. Anything milder produces no row; the brief is not
# a weather report. Tune in config.weather.thresholds.
DEFAULT_THRESHOLDS = {
    "rain_mm": 5.0,        # precipitation_sum
    "snow_cm": 1.0,        # snowfall_sum
    "heat_c": 35.0,        # temperature_2m_max
    "cold_c": -15.0,       # temperature_2m_min
    "wind_kmh": 60.0,      # windspeed_10m_max
}


def _c_to_f(c: float) -> float:
    return c * 9 / 5 + 32


def classify(day: dict, thr: dict, imperial: bool) -> tuple[str | None, str]:
    """Return (severity, note) for one day of daily weather values, or (None, '') if mild."""
    parts, sev = [], None
    rain = day.get("precipitation_sum") or 0.0
    snow = day.get("snowfall_sum") or 0.0
    tmax = day.get("temperature_2m_max")
    tmin = day.get("temperature_2m_min")
    wind = day.get("windspeed_10m_max") or 0.0
    if snow >= thr["snow_cm"]:
        sev = "snow"
        parts.append(f"snow {snow/2.54:.1f} in" if imperial else f"snow {snow:.0f} cm")
    elif rain >= thr["rain_mm"]:
        sev = "rain"
        parts.append(f"rain {rain/25.4:.2f} in" if imperial else f"rain {rain:.0f} mm")
    if tmax is not None and tmax >= thr["heat_c"]:
        sev = sev or "heat"
        parts.append(f"high {_c_to_f(tmax):.0f}°F" if imperial else f"high {tmax:.0f}°C")
    if tmin is not None and tmin <= thr["cold_c"]:
        sev = sev or "cold"
        parts.append(f"low {_c_to_f(tmin):.0f}°F" if imperial else f"low {tmin:.0f}°C")
    if wind >= thr["wind_kmh"]:
        sev = sev or "wind"
        parts.append(f"wind {wind/1.609:.0f} mph" if imperial else f"wind {wind:.0f} km/h")
    return sev, ", ".join(parts)


def fetch_open_meteo(lat: float, lon: float, start: dt.date, end: dt.date, tz: str) -> dict[str, dict]:
    """Daily weather by date from Open-Meteo (archive for the past, forecast for the last
    few days). Returns {iso_date: {variable: value}}. No API key needed."""
    import urllib.parse
    import urllib.request

    vars_ = "precipitation_sum,snowfall_sum,temperature_2m_max,temperature_2m_min,windspeed_10m_max"
    out: dict[str, dict] = {}
    # The archive lags a few days; the forecast endpoint covers recent history with past_days.
    today = dt.date.today()
    archive_end = min(end, today - dt.timedelta(days=6))
    calls = []
    if start <= archive_end:
        calls.append(("https://archive-api.open-meteo.com/v1/archive", {"start_date": start.isoformat(), "end_date": archive_end.isoformat()}))
    if end > archive_end:
        past = min(92, (today - max(start, archive_end + dt.timedelta(days=1))).days + 1)
        calls.append(("https://api.open-meteo.com/v1/forecast", {"past_days": max(past, 1), "forecast_days": 1}))
    for url, extra in calls:
        q = {"latitude": lat, "longitude": lon, "daily": vars_, "timezone": tz, **extra}
        with urllib.request.urlopen(url + "?" + urllib.parse.urlencode(q), timeout=30) as resp:
            data = json.load(resp)
        daily = data.get("daily") or {}
        for i, d in enumerate(daily.get("time", [])):
            if start.isoformat() <= d <= end.isoformat():
                out[d] = {k: (daily.get(k) or [None])[i] if i < len(daily.get(k) or []) else None for k in vars_.split(",")}
    return out


def load_weather(cfg: dict, start: dt.date, end: dt.date, base_dir: Path) -> list[Row]:
    w = cfg.get("weather") or {}
    if not w.get("enabled"):
        return []
    thr = {**DEFAULT_THRESHOLDS, **(w.get("thresholds") or {})}
    imperial = (w.get("units") or "imperial").lower() == "imperial"
    rows: list[Row] = []

    provider = (w.get("provider") or "open-meteo").lower()
    if provider == "file":
        # CSV: date,unit,precipitation_sum,snowfall_sum,temperature_2m_max,temperature_2m_min,windspeed_10m_max (metric)
        p = Path(w["file"])
        if not p.is_absolute():
            p = base_dir / p
        with p.open() as fh:
            for r in csv.DictReader(fh):
                day = {k: (float(r[k]) if r.get(k) not in (None, "") else None)
                       for k in ("precipitation_sum", "snowfall_sum", "temperature_2m_max", "temperature_2m_min", "windspeed_10m_max")}
                sev, note = classify(day, thr, imperial)
                if sev:
                    rows.append({"date": _as_date(r["date"]), "scope": r["unit"], "kind": "weather", "note": note, "severity": sev, "source": "weather:file"})
        return rows

    if provider != "open-meteo":
        raise ValueError(f"Unknown weather provider: {provider}")

    locations: dict[str, dict] = dict(w.get("units") or {})
    loc_file = w.get("locations_file")
    if loc_file:
        p = Path(loc_file)
        if not p.is_absolute():
            p = base_dir / p
        with p.open() as fh:
            for r in csv.DictReader(fh):
                locations[r["unit"]] = {"lat": float(r["lat"]), "lon": float(r["lon"])}
    if not locations:
        return []

    tz = cfg.get("business", {}).get("timezone") or "UTC"
    cache_path = base_dir / (cfg.get("output", {}).get("dir", "out")) / "weather_cache.json"
    cache: dict[str, dict] = {}
    if cache_path.exists():
        try:
            cache = json.loads(cache_path.read_text())
        except Exception:
            cache = {}

    for unit, loc in locations.items():
        key = f"{loc['lat']:.3f},{loc['lon']:.3f}"
        have = cache.get(key, {})
        need_start = start
        # extend the cache only for the dates we do not have
        missing = [d for d in _daterange(start, end) if d.isoformat() not in have]
        if missing:
            fetched = fetch_open_meteo(float(loc["lat"]), float(loc["lon"]), missing[0], missing[-1], tz)
            have.update(fetched)
            cache[key] = have
        for d in _daterange(need_start, end):
            day = have.get(d.isoformat())
            if not day:
                continue
            sev, note = classify(day, thr, imperial)
            if sev:
                rows.append({"date": d, "scope": unit, "kind": "weather", "note": note, "severity": sev, "source": "weather:open-meteo"})

    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(cache))
    except OSError:
        pass
    return rows


def _daterange(start: dt.date, end: dt.date):
    d = start
    while d <= end:
        yield d
        d += dt.timedelta(days=1)


# ---------------------------------------------------------------- lookup -----------------

class Context:
    def __init__(self, rows: list[Row]):
        self.rows = [n for n in (_norm(r) for r in rows) if n]
        self.by_date: dict[dt.date, list[Row]] = {}
        for r in self.rows:
            self.by_date.setdefault(r["date"], []).append(r)

    def on(self, day: dt.date, scope: str | None = None) -> list[Row]:
        rows = self.by_date.get(day, [])
        if scope is None:
            return rows
        return [r for r in rows if r["scope"] == scope]

    def global_on(self, day: dt.date) -> list[Row]:
        return [r for r in self.by_date.get(day, []) if r["scope"] == "all"]

    def weather_units(self, day: dt.date) -> list[Row]:
        return [r for r in self.by_date.get(day, []) if r["kind"] == "weather" and r["scope"] != "all"]

    def channel_on(self, day: dt.date, channel: str) -> list[Row]:
        return [r for r in self.by_date.get(day, []) if r["scope"] == f"channel:{channel}"]

    def summary(self, day: dt.date, total_units: int, voc: dict) -> str:
        """One sentence that can hang off a top-line flag: global rows today, global rows from
        the day before that still matter (a promo ending, a price change), channel rows, and a
        count of units with notable weather."""
        parts = []
        for r in self.global_on(day):
            parts.append(f"{r['kind']}: {r['note']}" if r["note"] else r["kind"])
        for r in self.global_on(day - dt.timedelta(days=1)):
            if r["kind"] in ("promo", "pricing", "outage", "event"):
                parts.append(f"day before, {r['kind']}: {r['note']}")
        for r in self.by_date.get(day, []):
            if r["scope"].startswith("channel:"):
                parts.append(f"{r['scope'][8:]} {r['kind']}: {r['note']}")
        wx = self.weather_units(day)
        if wx and total_units:
            by_sev: dict[str, int] = {}
            for r in wx:
                by_sev[r["severity"]] = by_sev.get(r["severity"], 0) + 1
            parts.append("weather: " + ", ".join(f"{s} at {n} of {total_units} {voc.get('units', 'units')}" for s, n in sorted(by_sev.items(), key=lambda x: -x[1])))
        return "; ".join(parts)
