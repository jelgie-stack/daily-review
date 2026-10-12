# Setup and tuning

Once per business. Fifteen minutes if the fact table already exists.

## Install

```bash
git clone https://github.com/jelgie-stack/daily-review && cd daily-review
python3 --version                      # 3.10 or newer
pip install -r requirements.txt        # pyyaml, duckdb
# plus one warehouse client if you are not using DuckDB:
#   pip install google-cloud-bigquery | snowflake-connector-python | psycopg2-binary
python sample/generate.py && python -m review.run --config config/config.example.yaml --date 2026-10-08
```

If the last command prints a brief, the install is good.

**As a Claude skill:** the repo folder *is* the skill (`SKILL.md` at the root). Copy or symlink
it into your skills directory, or zip it with `SKILL.md` at the top level and install the
bundle. Schedule "run the daily review" for each morning after the warehouse loads.

## Configure

1. Copy `config/config.example.yaml` to `config/config.yaml` (or start from the BigQuery,
   Snowflake, or restaurant example in the same folder).
2. Fill in `source` and the `columns` / `measures` expressions in your warehouse's SQL. That is
   the whole integration; see [adapters.md](adapters.md).
3. Pick a `profile`: `generic`, `restaurant`, `ecommerce`. Vocabulary and defaults only; see
   `profiles/`.
4. Add `holidays:` for anything the US calendar lacks, `context:` for internal events, and
   `weather:` if the business is weather-sensitive. See [context.md](context.md).

## Tune the floors

The floors matter more than the z threshold.

| rule | meaning | start with |
|---|---|---|
| `min_signal_revenue` | smallest top-line move anyone would act on | 2–3% of a typical day |
| `unit_move_abs` | same, for one unit | 15% of a typical unit-day |
| `unit_move_pct` | relative bar for a unit | 0.15 |
| `baseline_weeks` | same-weekday observations in the baseline | 8 |
| `z_threshold` | robust z that counts as unusual | 2.0 |

Run it for a week and read it with the owner of the numbers:

- **Everything is flagged:** floors too low, or a lumpy segment (catering, wholesale, B2B) is
  in the core. Raise the floors, or exclude the segment via the profile's
  `segments.exclude_from_core` plus a filter predicate.
- **Nothing is ever flagged:** floors too high, or `baseline_weeks` spans a step change (new
  units, a price increase). Lower the floors or shorten the baseline.
- **A holiday looks like a disaster:** it should not. Check the date is in
  `profiles/holidays.yaml` or add it under `holidays:` in config.
- **New units dominate the movers table:** their baselines are still climbing. Exclude them
  from the core with a filter until they have eight clean weeks.
