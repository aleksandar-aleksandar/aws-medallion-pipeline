"""
Gold layer: compute metrics and KPIs from silver Parquet and write gold Parquet tables.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from common import metric_date_from_event
from transform import run_gold_transform

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
    silver_prefix = os.environ.get("SILVER_PREFIX", "silver")
    gold_prefix = os.environ.get("GOLD_PREFIX", "gold")
    metric_date = metric_date_from_event(event)

    logger.info("Gold transform metric_date=%s", metric_date.isoformat())
    result = run_gold_transform(
        bucket=bucket,
        silver_prefix=silver_prefix,
        gold_prefix=gold_prefix,
        metric_date=metric_date,
    )
    logger.info("Gold transform complete: %s", result)
    return result
