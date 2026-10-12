---
name: daily-review
description: >-
  Runs a morning business review that only flags changes that are real. Use when the user says
  "run the daily review", "morning brief", "how did yesterday go", "daily numbers", or when a
  scheduled task fires with one of those phrases. Pulls yesterday's revenue and orders by unit and
  channel from the configured warehouse, compares every number to its same-weekday baseline,
  splits revenue moves into volume vs value, checks whether a move is a trend or a one-off, lists
  the units that moved, and points each flag at a diagnostic playbook. Works for any business with
  a daily revenue stream (profiles: generic, restaurant, ecommerce). Delivers the brief in chat and
  as a Markdown file. Never creates emails or messages on its own.
---

# Daily Review

A morning brief for someone who runs a business and has two minutes. The method has four rules,
and every step below exists to enforce one of them:

1. **Compare like with like.** A Tuesday is judged against the last eight Tuesdays, never
   against Monday or against a monthly average.
2. **Explain revenue before reporting it.** Revenue = volume × value. Say which one moved.
3. **Don't cry wolf.** A move has to be statistically unusual (robust z ≥ 2), big enough to
   matter (a currency floor), and, to be called a trend, pointing the same way on 2 of the last
   3 days.
4. **Every flag comes with a next step.** Each flag names a playbook in `diagnostics/`.
5. **A holiday is not a bad weekday.** Holidays leave the baselines, get compared to the same
   holiday last year, and never start a trend.

## Setup (once per business)

1. Copy `config/config.example.yaml` to `config/config.yaml` (or start from the BigQuery,
   Snowflake, or restaurant example).
2. Fill in `source` and the `columns` / `measures` expressions in your warehouse's SQL. That is
   the whole integration: the engine issues one `GROUP BY` query. See `docs/adapters.md`.
3. Pick a `profile` (`generic`, `restaurant`, `ecommerce`) and tune `rules` to the size of the
   business. The floors matter more than the z threshold: set `min_signal_revenue` to the
   smallest daily revenue move anyone would act on, and `unit_move_abs` to the same for a
   single unit.
4. Run `python -m review.run --config config/config.yaml` once and read the brief with the
   owner of the numbers. Adjust floors until the quiet days are quiet.

## Running the review

**Preferred: Python is available.**

```bash
python -m review.run --config config/config.yaml            # yesterday, business time zone
python -m review.run --config config/config.yaml --date 2026-10-08
```

The brief prints to stdout and lands in `out/YYYYMMDD-daily-review.md` with a JSON twin.

**Fallback: no Python, but a warehouse connector (MCP) is available.**

1. `python -m review.run --config config/config.yaml --print-sql` prints the exact query. If
   even that is not possible, build it by hand from `review/query.py`: it is a dozen lines.
2. Run the query through the connector and save the rows as CSV or JSON.
3. `python -m review.run --config config/config.yaml --rows rows.csv` does the analysis
   offline.

Do not try to reproduce the statistics in your head. The baselines, z-scores and
decomposition are the product; a brief without them is a guess.

## Delivering the brief

- Paste the full brief into chat. Lead with the verdict line, then "What needs attention".
- When a flag names a playbook, open it (`diagnostics/<name>.md`) and run its checks with the
  tools available (the warehouse connector, analytics, the CRM). Add what you find under the
  flag as sub-bullets. Stop when a check explains the move; say so plainly.
- If the data for the review date is missing, say that and stop. Do not fall back to an
  older date without telling the user.
- Never send the brief anywhere (email, chat tools) unless the user asks in that session.

## When the brief is wrong

- **Everything is flagged.** The floors are too low or a lumpy segment (catering, wholesale,
  B2B) is mixed into the core. Raise `min_signal_revenue` / `unit_move_abs`, or move the
  segment to `segments.exclude_from_core` via the profile and give it a filter.
- **Nothing is ever flagged.** The floors are too high, or `baseline_weeks` spans a period
  with a step change (new stores, a price increase). Shorten the baseline.
- **A holiday looks like a disaster.** It should not: the calendar in `profiles/holidays.yaml`
  switches a holiday to a same-holiday-last-year comparison and keeps holidays out of
  baselines. If a local holiday or event is missing, add it under `holidays:` in config.

## Files

- `review/` — engine: `config.py`, `query.py`, `stats.py`, `analyze.py`, `brief.py`, `run.py`
- `adapters/` — DuckDB, BigQuery, Snowflake, Postgres/Redshift (one method each)
- `profiles/` — vocabulary and default rules per kind of business
- `diagnostics/` — the playbooks flags point to
- `docs/method.md` — why each rule exists; `docs/adapters.md` — hooking up a warehouse
- `sample/` — a fake business with planted anomalies so the whole thing runs offline
