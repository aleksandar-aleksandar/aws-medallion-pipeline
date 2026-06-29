"""Load gold Parquet tables from S3 into PostgreSQL for Superset."""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

GOLD_TABLES: tuple[str, ...] = (
    "daily_hn_post_counts",
    "daily_active_users",
    "daily_users_metric",
    "top_x_users_by_followers",
    "top_hn_users_by_karma_high",
    "top_hn_users_by_karma_low",
    "top_hn_jobs_by_score",
    "top_hn_posts_by_score",
    "data_quality_score",
)


def _pg_connect() -> Any:
    import pg8000

    return pg8000.connect(
        host=os.environ["POSTGRES_HOST"],
        port=int(os.environ.get("POSTGRES_PORT", "5432")),
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        database=os.environ["POSTGRES_DB"],
        timeout=60,
    )


def _ensure_schema(connection: Any) -> None:
    cursor = connection.cursor()
    try:
        cursor.execute("CREATE SCHEMA IF NOT EXISTS gold")
        connection.commit()
    finally:
        cursor.close()


def load_gold_to_postgres(*, bucket: str, gold_prefix: str) -> dict[str, Any]:
    import awswrangler as wr

    gold_prefix = gold_prefix.strip("/")
    conn = _pg_connect()
    _ensure_schema(conn)

    loaded: dict[str, int] = {}
    skipped: list[str] = []

    try:
        for table in GOLD_TABLES:
            path = f"s3://{bucket}/{gold_prefix}/{table}/"
            try:
                df = wr.s3.read_parquet(path=path, dataset=True)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Skip table %s (read failed): %s", table, exc)
                skipped.append(table)
                continue

            if df.empty:
                skipped.append(table)
                continue

            wr.postgresql.to_sql(
                df=df,
                con=conn,
                table=table,
                schema="gold",
                mode="overwrite",
                use_column_names=True,
            )
            loaded[table] = len(df)
            logger.info("Loaded %s rows into gold.%s", len(df), table)
    finally:
        conn.close()

    return {
        "status": "ok",
        "tables_loaded": loaded,
        "tables_skipped": skipped,
        "postgres_schema": "gold",
    }
