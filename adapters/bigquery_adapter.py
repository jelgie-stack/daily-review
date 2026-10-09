from __future__ import annotations

from . import Adapter


class BigQueryAdapter(Adapter):
    """Google BigQuery via google-cloud-bigquery. Auth: Application Default Credentials."""

    name = "bigquery"

    def run(self, sql: str) -> list[dict]:
        from google.cloud import bigquery  # pip install google-cloud-bigquery

        client = bigquery.Client(
            project=self.settings.get("project"), location=self.settings.get("location")
        )
        job = client.query(sql)
        return [dict(row.items()) for row in job.result()]
