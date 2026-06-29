"""Lambda: copy gold metrics from S3 Parquet into PostgreSQL on the analytics EC2 host."""

from __future__ import annotations

import logging
import os
from typing import Any

from load import load_gold_to_postgres

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
    gold_prefix = os.environ.get("GOLD_PREFIX", "gold")

    logger.info("Loading gold tables from s3://%s/%s/ to PostgreSQL", bucket, gold_prefix)
    result = load_gold_to_postgres(bucket=bucket, gold_prefix=gold_prefix)
    logger.info("Gold load complete: %s", result)
    return result
