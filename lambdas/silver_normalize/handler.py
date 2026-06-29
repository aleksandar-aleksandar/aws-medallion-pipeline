"""
Silver layer: normalize bronze Hacker News JSON and X CSV into partitioned Parquet tables.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from normalize import content_date_from_event, run_silver_normalize

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def _env(name: str, default: str | None = None) -> str:
    value = os.environ.get(name, default)
    if value is None or value == "":
        raise ValueError(f"Missing required environment variable: {name}")
    return value


def lambda_handler(event: dict[str, Any] | None, context: Any) -> dict[str, Any]:
    event = event or {}
    bucket = _env("DATA_LAKE_BUCKET")
    bronze_prefix = os.environ.get("BRONZE_PREFIX", "bronze")
    silver_prefix = os.environ.get("SILVER_PREFIX", "silver")
    process_x = str(event.get("process_x", os.environ.get("PROCESS_X", "true"))).lower() != "false"

    content_date = content_date_from_event(event)
    logger.info(
        "Silver normalize content_date=%s process_x=%s",
        content_date.isoformat(),
        process_x,
    )

    import boto3

    s3 = boto3.client("s3")
    result = run_silver_normalize(
        s3_client=s3,
        bucket=bucket,
        bronze_prefix=bronze_prefix,
        silver_prefix=silver_prefix,
        content_date=content_date,
        process_x=process_x,
    )
    logger.info("Silver normalize complete: %s", result)
    return result
