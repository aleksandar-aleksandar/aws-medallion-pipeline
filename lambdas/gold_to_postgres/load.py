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

# Top-N tables are written per metric date; Postgres should expose one snapshot for charts.
LATEST_DATE_TABLES: frozenset[str] = frozenset(
    {
        "top_x_users_by_followers",
        "top_hn_users_by_karma_high",
        "top_hn_users_by_karma_low",
        "top_hn_jobs_by_score",
        "top_hn_posts_by_score",
    }
)


def _latest_date_slice(df: Any, *, limit: int | None = None) -> Any:
    if df.empty or "date" not in df.columns:
        return df
    dates = df["date"].astype(str)
    latest = dates.max()
    sliced = df[dates == latest].copy()
    if limit is not None and len(sliced) > limit:
        if "rank" in sliced.columns:
            sliced = sliced.sort_values("rank").head(limit)
        else:
            sliced = sliced.head(limit)
    logger.info("Keeping latest date=%s (%s rows)", latest, len(sliced))
    return sliced


def _normalize_gold_frame(df: Any, table: str) -> Any:
    import pandas as pd

    if df.empty:
        return df
    if table in {"top_hn_users_by_karma_high", "top_hn_users_by_karma_low"} and "karma_score" in df.columns:
        df = df.copy()
        df["karma_score"] = pd.to_numeric(df["karma_score"], errors="coerce")
    return df


def _read_gold_parquet(path: str, table: str) -> Any:
    import awswrangler as wr

    try:
        return wr.s3.read_parquet(path=path, dataset=True)
    except Exception as exc:
        if "incompatible types" not in str(exc).lower():
            raise
        logger.warning("Partition schema mismatch for %s, reading files individually", table)
        files = wr.s3.list_objects(path)
        parquet_files = [f for f in files if f.endswith(".parquet")]
        if not parquet_files:
            raise
        frames = [wr.s3.read_parquet(path=f) for f in parquet_files]
        import pandas as pd

        return pd.concat(frames, ignore_index=True)


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
                df = _read_gold_parquet(path, table)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Skip table %s (read failed): %s", table, exc)
                skipped.append(table)
                continue

            if df.empty:
                skipped.append(table)
                continue

            df = _normalize_gold_frame(df, table)

            if table in LATEST_DATE_TABLES:
                row_limit = 10 if table.startswith("top_") else None
                df = _latest_date_slice(df, limit=row_limit)

            if table in {"top_hn_users_by_karma_high", "top_hn_users_by_karma_low"} and not df.empty:
                import pandas as pd

                df = df.copy()
                if "date" in df.columns:
                    df["_date_key"] = df["date"].astype(str)
                    df = df.sort_values(["_date_key", "rank"], ascending=[False, True]).drop(
                        columns=["_date_key"]
                    )
                else:
                    df = df.sort_values("rank")
                df = df.drop_duplicates(subset=["rank"], keep="first").head(10)

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
