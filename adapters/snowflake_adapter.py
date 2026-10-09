from __future__ import annotations

import os

from . import Adapter


class SnowflakeAdapter(Adapter):
    """Snowflake via snowflake-connector-python. Password from SNOWFLAKE_PASSWORD, or key-pair
    auth from SNOWFLAKE_PRIVATE_KEY_PATH."""

    name = "snowflake"

    def run(self, sql: str) -> list[dict]:
        import snowflake.connector  # pip install snowflake-connector-python

        kwargs = {
            k: self.settings[k]
            for k in ("account", "user", "role", "warehouse", "database", "schema")
            if k in self.settings
        }
        key_path = os.environ.get("SNOWFLAKE_PRIVATE_KEY_PATH")
        if key_path:
            kwargs["private_key_file"] = key_path
        else:
            kwargs["password"] = os.environ["SNOWFLAKE_PASSWORD"]
        con = snowflake.connector.connect(**kwargs)
        try:
            cur = con.cursor()
            cur.execute(sql)
            cols = [d[0].lower() for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
        finally:
            con.close()
