"""Warehouse adapters.

Every adapter exposes one method: ``run(sql) -> list[dict]``. The engine never issues anything
but ANSI SQL (``CAST(... AS DATE)``, ``DATE 'yyyy-mm-dd'`` literals, ``GROUP BY`` ordinals), so an
adapter is just a connection and a cursor. Credentials are read from the environment, never
from config.
"""

from __future__ import annotations

from typing import Any


class Adapter:
    name = "base"

    def __init__(self, settings: dict[str, Any] | None = None):
        self.settings = settings or {}

    def run(self, sql: str) -> list[dict]:  # pragma: no cover - interface
        raise NotImplementedError


class PrintOnly(Adapter):
    """Used by ``--print-sql``: prints the query instead of running it, so the same SQL can be
    pasted into a warehouse console or run through an MCP connector."""

    name = "print"

    def run(self, sql: str) -> list[dict]:
        print(sql)
        return []


def get_adapter(cfg: dict[str, Any], print_only: bool = False) -> Adapter:
    if print_only:
        return PrintOnly()
    wh = cfg.get("warehouse", {})
    kind = (wh.get("adapter") or "duckdb").lower()
    settings = wh.get(kind, {})
    if kind == "duckdb":
        from .duckdb_adapter import DuckDBAdapter

        return DuckDBAdapter(settings)
    if kind == "bigquery":
        from .bigquery_adapter import BigQueryAdapter

        return BigQueryAdapter(settings)
    if kind == "snowflake":
        from .snowflake_adapter import SnowflakeAdapter

        return SnowflakeAdapter(settings)
    if kind in ("postgres", "postgresql", "redshift"):
        from .postgres_adapter import PostgresAdapter

        return PostgresAdapter(settings)
    raise ValueError(f"Unknown warehouse adapter: {kind}")
