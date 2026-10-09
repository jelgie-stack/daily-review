# daily-review

A morning business brief that only flags what is real.

Every number is compared to its **same-weekday baseline**, revenue moves are **split into
volume vs value**, a move is only called a trend if it **persists**, and every flag comes
with a **diagnostic playbook**. It runs against any SQL warehouse through one `GROUP BY`
query, and it ships as a [Claude skill](SKILL.md) so an agent can run it every morning and
work the playbooks with whatever tools it has.

```
# Juniper Kitchen: Thursday Oct 8, 2026

**Soft, and it is a trend: revenue -9.5% vs baseline today, and below baseline on 2 of the last 3 days.**

## What needs attention

- 🔴 Revenue is -9.5% vs the same-weekday baseline. Fewer checks cost -$1,885; a higher average check clawed back $651.  Playbook: diagnostics/volume_drop.md
- 🟠 New customers are -38.2% vs baseline (126 vs a typical 204).  Playbook: diagnostics/new_customer_drop.md
- 🔴 1 store is off by 15%+ vs its own baseline (U07). U07 was down yesterday too.  Playbook: diagnostics/unit_drop.md
- 🟡 Channel mix moved: in-store is -5.8 pts of revenue share vs its usual 55%.  Playbook: diagnostics/channel_shift.md
```

Full sample output: [restaurant profile](sample/sample_brief.md) · [generic profile](sample/sample_brief_generic.md).

## Why this exists

Dashboards show everything and explain nothing, so people stop reading them. The rules here
came from running a daily review for a multi-unit business and learning, one false alarm at a
time, what a reader actually needs:

1. **Compare like with like.** A Tuesday is judged against the last eight Tuesdays. Never
   against Monday, never against a monthly average.
2. **Explain before reporting.** Revenue = orders × average order value. The brief says which
   one moved, because they have different owners.
3. **Don't cry wolf.** A move must be statistically unusual (robust z ≥ 2, median/MAD), big
   enough to act on (a currency floor), and, to be called a trend, pointing the same way on 2
   of the last 3 days.
4. **Every flag has a next step.** Flags point at playbooks in [`diagnostics/`](diagnostics/).

[docs/method.md](docs/method.md) goes through each rule and why it is there.

## Try it in two minutes

```bash
git clone https://github.com/jelgie-stack/daily-review && cd daily-review
pip install -r requirements.txt
python sample/generate.py                                   # fake business, planted anomalies
python -m review.run --config config/config.example.yaml --date 2026-10-08
```

The sample plants five anomalies on Oct 8 (a two-day volume slump, one store down two days, one
store down one day, a delivery share jump, a new-customer drop). The brief should find all five
and call the one-day store move a one-off. `--config config/config.restaurant.example.yaml` runs
the same data with restaurant vocabulary, dayparts, and catering reported separately.

## Point it at your warehouse

Copy `config/config.example.yaml` to `config/config.yaml` and fill in five expressions in your
warehouse's SQL:

```yaml
source: "`proj.marts.fct_orders`"
columns:
  date: business_date
  unit: store_id          # whatever you compare against itself: store, market, product line
  channel: order_channel
measures:
  revenue: SUM(net_sales)
  orders: COUNT(DISTINCT order_id)
```

That is the entire integration. The engine builds one query:

```sql
SELECT CAST(business_date AS DATE) AS d, store_id AS unit, order_channel AS channel,
       SUM(net_sales) AS revenue, COUNT(DISTINCT order_id) AS orders
FROM `proj.marts.fct_orders`
WHERE CAST(business_date AS DATE) BETWEEN DATE '2025-10-02' AND DATE '2026-10-08'
GROUP BY 1, 2, 3
```

and does the statistics in Python. Adapters exist for **BigQuery, Snowflake, Postgres,
Redshift and DuckDB**; adding one is a single method. `--print-sql` prints the query so you
can run it anywhere (including through an MCP connector) and feed the rows back with
`--rows`. Details in [docs/adapters.md](docs/adapters.md).

## Profiles, not forks

The engine is business-agnostic. A **profile** supplies vocabulary, default rules, optional
dimensions, and which segments to keep out of the core numbers:

| profile | unit | adds |
|---|---|---|
| `generic` | unit | revenue = orders × AOV, channel mix |
| `restaurant` | store | checks, dayparts from order hour, catering reported separately |
| `ecommerce` | market | sessions and conversion (orders = sessions × CVR) |

A profile is a YAML file in [`profiles/`](profiles/); write your own by extending `generic`.

## As a Claude skill

[`SKILL.md`](SKILL.md) tells Claude when to run the review, how to run it (Python, or
`--print-sql` plus a warehouse connector), how to deliver the brief, and how to work the
playbook for each flag with the tools it has. Install the repo folder as a skill and schedule
"run the daily review" for each morning.

## Layout

```
review/        engine: config → query → stats → analyze → brief
adapters/      duckdb, bigquery, snowflake, postgres (one method each)
profiles/      generic, restaurant, ecommerce
diagnostics/   playbooks the flags point to
config/        example configs for each warehouse and profile
sample/        synthetic data generator + sample briefs
docs/          method.md (why), adapters.md (how)
tests/         python -m unittest
```

## Tuning

The floors matter more than the z threshold. Set `rules.min_signal_revenue` to the smallest
daily move anyone would act on, and `rules.unit_move_abs` to the same for one unit. Run it for
a week; if quiet days are not quiet, raise the floors or move a lumpy segment (catering,
wholesale) out of the core.

## Not included, on purpose

A holiday calendar, forecasting, and root-cause from data alone. The engine finds where and how
much; the playbooks are for a person, or an agent with tools, to find why.

## License

MIT. Built from the method, not from any employer's code or data; the sample business is
invented.
