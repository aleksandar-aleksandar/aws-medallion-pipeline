"""Read silver Parquet, compute gold metrics, write gold Parquet to S3."""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

import pandas as pd

from common import metric_date_from_event
from metrics import compute_all_metrics

logger = logging.getLogger(__name__)


def read_silver_tables(bucket: str, silver_prefix: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    import awswrangler as wr

    silver_prefix = silver_prefix.strip("/")
    users_path = f"s3://{bucket}/{silver_prefix}/users/"
    posts_path = f"s3://{bucket}/{silver_prefix}/posts/"

    users_df = wr.s3.read_parquet(path=users_path, dataset=True)
    posts_df = wr.s3.read_parquet(path=posts_path, dataset=True)
    logger.info("Loaded silver users=%s posts=%s", len(users_df), len(posts_df))
    return users_df, posts_df


def _write_table(
    df: pd.DataFrame,
    *,
    bucket: str,
    gold_prefix: str,
    table_name: str,
    partition_cols: list[str] | None,
) -> int:
    import awswrangler as wr

    if df.empty:
        logger.warning("Skipping empty gold table %s", table_name)
        return 0

    path = f"s3://{bucket}/{gold_prefix.strip('/')}/{table_name}/"
    kwargs: dict[str, Any] = {
        "df": df,
        "path": path,
        "dataset": True,
        "mode": "overwrite_partitions",
        "compression": "snappy",
    }
    if partition_cols:
        kwargs["partition_cols"] = partition_cols

    wr.s3.to_parquet(**kwargs)
    return len(df)


def write_gold_tables(
    tables: dict[str, pd.DataFrame],
    *,
    bucket: str,
    gold_prefix: str,
) -> dict[str, Any]:
    partition_map: dict[str, list[str] | None] = {
        "daily_hn_post_counts": ["date"],
        "daily_active_users": ["platform_partition", "date"],
        "daily_users_metric": ["platform_partition", "date"],
        "top_x_users_by_followers": ["date"],
        "top_hn_users_by_karma_high": ["date"],
        "top_hn_users_by_karma_low": ["date"],
        "top_hn_jobs_by_score": ["date"],
        "top_hn_posts_by_score": ["date"],
        "data_quality_score": ["date"],
    }

    written: dict[str, int] = {}
    for table_name, frame in tables.items():
        count = _write_table(
            frame,
            bucket=bucket,
            gold_prefix=gold_prefix,
            table_name=table_name,
            partition_cols=partition_map.get(table_name),
        )
        written[table_name] = count
    return written


def run_gold_transform(
    *,
    bucket: str,
    silver_prefix: str,
    gold_prefix: str,
    metric_date: date,
) -> dict[str, Any]:
    users_df, posts_df = read_silver_tables(bucket, silver_prefix)
    tables = compute_all_metrics(users_df, posts_df, metric_date)
    written = write_gold_tables(tables, bucket=bucket, gold_prefix=gold_prefix)

    return {
        "status": "ok",
        "metric_date": metric_date.isoformat(),
        "gold_prefix": f"s3://{bucket}/{gold_prefix.strip('/')}/",
        "tables_written": written,
    }
