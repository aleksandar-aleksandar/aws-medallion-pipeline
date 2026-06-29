"""Orchestrate silver normalization and Parquet writes to S3."""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable

import pandas as pd

from common import PLATFORM_HN, PLATFORM_PARTITION_HN, PLATFORM_PARTITION_X, dedupe_posts, dedupe_users, partition_date_parts
from hn import normalize_hn_bronze_keys
from x_twitter import normalize_x_bronze_keys

logger = logging.getLogger(__name__)


def content_date_from_event(event: dict[str, Any] | None) -> date:
    event = event or {}
    override = event.get("content_date") or event.get("CONTENT_DATE")
    if override:
        return date.fromisoformat(str(override))
    return datetime.now(timezone.utc).date() - timedelta(days=1)


def _platform_partition_value(platform: str) -> str:
    if platform == PLATFORM_HN:
        return PLATFORM_PARTITION_HN
    return PLATFORM_PARTITION_X


def _prepare_users_df(rows: list[dict[str, Any]]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(
            columns=[
                "user_id",
                "username",
                "platform",
                "karma_score",
                "follower_count",
                "is_verified",
                "created_at",
                "platform_partition",
            ]
        )
    df = pd.DataFrame(rows)
    df["platform_partition"] = df["platform"].map(_platform_partition_value)
    return df


def _prepare_posts_df(rows: list[dict[str, Any]]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(
            columns=[
                "post_id",
                "author_username",
                "content_text",
                "created_at",
                "post_type",
                "platform",
                "parent_id",
                "story_id",
                "child_ids",
                "points",
                "year",
                "month",
                "day",
            ]
        )
    df = pd.DataFrame(rows)
    parts = df["created_at"].apply(partition_date_parts)
    df["year"] = parts.apply(lambda p: p["year"])
    df["month"] = parts.apply(lambda p: p["month"])
    df["day"] = parts.apply(lambda p: p["day"])
    return df


def list_s3_keys(s3_client: Any, bucket: str, prefix: str) -> list[str]:
    keys: list[str] = []
    paginator = s3_client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            keys.append(obj["Key"])
    return keys


def read_s3_json(s3_client: Any, bucket: str) -> Callable[[str], dict[str, Any]]:
    def _read(key: str) -> dict[str, Any]:
        import json

        body = s3_client.get_object(Bucket=bucket, Key=key)["Body"].read()
        return json.loads(body.decode("utf-8"))

    return _read


def read_s3_text(s3_client: Any, bucket: str) -> Callable[[str], str]:
    def _read(key: str) -> str:
        body = s3_client.get_object(Bucket=bucket, Key=key)["Body"].read()
        return body.decode("utf-8", errors="replace")

    return _read


def write_silver_parquet(
    *,
    users_df: pd.DataFrame,
    posts_df: pd.DataFrame,
    bucket: str,
    silver_prefix: str,
) -> dict[str, Any]:
    import awswrangler as wr

    users_path = f"s3://{bucket}/{silver_prefix.strip('/')}/users/"
    posts_path = f"s3://{bucket}/{silver_prefix.strip('/')}/posts/"

    users_written = 0
    posts_written = 0

    if not users_df.empty:
        wr.s3.to_parquet(
            df=users_df,
            path=users_path,
            dataset=True,
            mode="overwrite_partitions",
            partition_cols=["platform_partition"],
            compression="snappy",
        )
        users_written = len(users_df)

    if not posts_df.empty:
        wr.s3.to_parquet(
            df=posts_df,
            path=posts_path,
            dataset=True,
            mode="overwrite_partitions",
            partition_cols=["year", "month", "day"],
            compression="snappy",
        )
        posts_written = len(posts_df)

    return {
        "users_path": users_path,
        "posts_path": posts_path,
        "users_written": users_written,
        "posts_written": posts_written,
    }


def run_silver_normalize(
    *,
    s3_client: Any,
    bucket: str,
    bronze_prefix: str,
    silver_prefix: str,
    content_date: date,
    process_x: bool = True,
) -> dict[str, Any]:
    bronze_prefix = bronze_prefix.strip("/")
    silver_prefix = silver_prefix.strip("/")

    hn_prefix = f"{bronze_prefix}/hackernews/content_date={content_date.isoformat()}/"
    hn_keys = list_s3_keys(s3_client, bucket, hn_prefix)
    logger.info("HN bronze keys for %s: %s", content_date.isoformat(), len(hn_keys))

    hn_users, hn_posts = normalize_hn_bronze_keys(hn_keys, read_json=read_s3_json(s3_client, bucket))

    x_users: list[dict[str, Any]] = []
    x_posts: list[dict[str, Any]] = []
    if process_x:
        x_prefix = f"{bronze_prefix}/x/"
        x_keys = list_s3_keys(s3_client, bucket, x_prefix)
        logger.info("X bronze keys: %s", len(x_keys))
        x_users, x_posts = normalize_x_bronze_keys(x_keys, read_text=read_s3_text(s3_client, bucket))

    users = dedupe_users(hn_users + x_users)
    posts = dedupe_posts(hn_posts + x_posts)

    users_df = _prepare_users_df(users)
    posts_df = _prepare_posts_df(posts)

    write_result = write_silver_parquet(
        users_df=users_df,
        posts_df=posts_df,
        bucket=bucket,
        silver_prefix=silver_prefix,
    )

    return {
        "status": "ok",
        "content_date": content_date.isoformat(),
        "hn_keys_processed": len(hn_keys),
        "hn_users": len(hn_users),
        "hn_posts": len(hn_posts),
        "x_users": len(x_users),
        "x_posts": len(x_posts),
        "users_deduped": len(users),
        "posts_deduped": len(posts),
        **write_result,
    }
