from __future__ import annotations

import os

from . import Adapter


class PostgresAdapter(Adapter):
    """Postgres and Redshift via psycopg2. DSN from config; password from PGPASSWORD or the DSN."""

    name = "postgres"

    def run(self, sql: str) -> list[dict]:
        import psycopg2  # pip install psycopg2-binary

        dsn = self.settings.get("dsn") or os.environ["DATABASE_URL"]
        con = psycopg2.connect(dsn)
        try:
            cur = con.cursor()
            cur.execute(sql)
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
        finally:
            con.close()
