# Context rows

Context is what explains a day that the sales data cannot: a promo, an outage, reduced hours, a
price change, notable weather. It is attached to the flag it explains. It never removes one.

## Format

CSV (`context.file`) or inline (`context.rows`), same columns:

| column | values |
|---|---|
| `date` | `YYYY-MM-DD`, the day the thing happened |
| `scope` | `all`, a unit id (`U07`), or `channel:<name>` (`channel:online`) |
| `kind` | `promo`, `outage`, `hours`, `pricing`, `event`, `competitor`, `weather`, or a plain word |
| `note` | one line, specific: "Fall BOGO ended", "closed 2pm to close, cooler failure" |
| `severity` | optional: `low`, `medium`, `high` |
| `source` | where it came from: `user`, `manual`, `agent:email`, `agent:slack`, `weather:open-meteo` |

```
date,scope,kind,note,severity,source
2026-10-07,all,promo,"Fall BOGO ended",,manual
2026-10-07,U07,outage,"Walk-in cooler failed; closed 2pm to close",high,manual
2026-10-08,channel:online,outage,"Checkout 502s 11:40 to 12:25",medium,agent:email
```

## How the brief uses it

- A row scoped `all` on the review date, or a `promo`/`pricing`/`outage`/`event` row from the
  day before, goes into the one-line summary on the verdict and the first top-line flag.
- A unit row shows in the unit table and on the unit flag.
- A channel row attaches to the channel-mix flag.
- Weather rows are summarised as "rain at 6 of 12 stores" on the top line and listed per unit
  in the Context section.

## Weather

Opt in with `weather.enabled: true`. Two providers:

- `open-meteo` (default): free, no API key. Needs a latitude/longitude per unit, in
  `weather.units` (a map) or `weather.locations_file` (CSV: `unit,lat,lon`). Results are
  cached in `<output.dir>/weather_cache.json` so each run fetches only missing days.
- `file`: a CSV of daily metric values per unit
  (`date,unit,precipitation_sum,snowfall_sum,temperature_2m_max,temperature_2m_min,windspeed_10m_max`).
  Use it when the review runs somewhere without internet, or for tests.

Only notable weather produces a row. Defaults, overridable under `weather.thresholds`:
rain ≥ 5 mm, snow ≥ 1 cm, high ≥ 35°C, low ≤ -15°C, wind ≥ 60 km/h. Display units are
`imperial` or `metric` (`weather.units`).

A weather fetch that fails adds a warning to the brief and nothing else. The numbers never
wait on the weather.

## Rules for an agent adding rows

1. Only add what you were told or read. A guessed explanation is worse than none, because it
   stops someone looking.
2. Always set `source` to where it came from.
3. One row per fact; a two-day outage is two rows.
4. Put internal events in, not news. "Fed raised rates" explains nothing about Tuesday.
