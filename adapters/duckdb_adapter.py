from __future__ import annotations

from . import Adapter


class DuckDBAdapter(Adapter):
    """Local DuckDB file. Used for the bundled sample and for anyone who exports a daily fact
    table to Parquet/CSV and wants to run the review without a warehouse connection."""

    name = "duckdb"

    def run(self, sql: str) -> list[dict]:
        import duckdb

        path = self.settings.get("path", ":memory:")
        con = duckdb.connect(path, read_only=path != ":memory:")
        try:
            cur = con.execute(sql)
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
        finally:
            con.close()
