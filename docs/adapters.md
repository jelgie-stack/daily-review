# Hooking up a warehouse

The engine needs one thing from your warehouse: daily totals by unit and channel. It gets them
with a single query that it builds from `config.yaml`:

```sql
SELECT
  CAST(<columns.date> AS DATE) AS d,
  <columns.unit>                AS unit,
  <columns.channel>             AS channel,
  [<extra dimensions>]
  <measures.revenue>            AS revenue,
  <measures.orders>             AS orders,
  [<optional measures>]
FROM <source>
WHERE CAST(<columns.date> AS DATE) BETWEEN DATE '...' AND DATE '...'
  AND (<filters.core[0]>) AND ...
  AND NOT (<excluded segment predicate>)
GROUP BY 1, 2, 3 [, ...]
```

Everything inside the angle brackets is pasted verbatim from your config, so you write them in
your warehouse's own SQL. Measures must be aggregates. That is the whole contract. Baselines,
z-scores, decomposition and persistence are computed in Python from the result, so the
warehouse never has to do anything a 20-year-old database could not.

## Three ways to run it

1. **Adapter (default).** `warehouse.adapter` picks one of `duckdb`, `bigquery`, `snowflake`,
   `postgres` (also Redshift). Install the matching client library and provide credentials
   through the environment:

   | adapter | pip install | credentials |
   |---|---|---|
   | duckdb | `duckdb` | none (local file) |
   | bigquery | `google-cloud-bigquery` | Application Default Credentials |
   | snowflake | `snowflake-connector-python` | `SNOWFLAKE_PASSWORD` or `SNOWFLAKE_PRIVATE_KEY_PATH` |
   | postgres / redshift | `psycopg2-binary` | `PGPASSWORD`, or a DSN in config / `DATABASE_URL` |

2. **Print and run elsewhere.** `--print-sql` prints the query. Run it in your console or through
   an MCP connector, save the rows as CSV or JSON, then `--rows rows.csv`. Useful when the
   review runs inside an agent that already has a warehouse tool.

3. **Export to DuckDB.** Dump your daily fact table to Parquet or CSV, load it into a DuckDB
   file, and point the `duckdb` adapter at it. No network, no credentials, same brief.

## Adding an adapter

An adapter is a class with one method:

```python
from adapters import Adapter

class MyWarehouse(Adapter):
    name = "mywarehouse"
    def run(self, sql: str) -> list[dict]:
        ...  # execute, return one dict per row keyed by the column aliases above
```

Register it in `adapters/get_adapter`. Column names in the returned dicts must match the
aliases (`d`, `unit`, `channel`, `revenue`, `orders`, ...); lower-case them if your driver
upper-cases (the Snowflake adapter does this).

## Dialect notes

The query avoids everything that varies between dialects. The only constructs it relies on:

- `CAST(x AS DATE)` — universal.
- `DATE 'yyyy-mm-dd'` literals — BigQuery, Snowflake, Postgres, Redshift, DuckDB, SQL Server
  2012+. (MySQL accepts `DATE 'yyyy-mm-dd'` too.)
- Ordinal `GROUP BY 1, 2, 3` — all of the above.

If your date column is a string, wrap it in your dialect's parse function inside
`columns.date` (`PARSE_DATE('%Y%m%d', dt)` in BigQuery, `TO_DATE(dt, 'YYYYMMDD')` in
Snowflake); the engine will still `CAST` the result, which is harmless.

## Grain

The source can be at order grain or already aggregated to day × unit × channel. Aggregate
measures work on both (`SUM` over daily rows is fine). The only thing that needs order grain is
a derived daypart (`columns.hour`).
