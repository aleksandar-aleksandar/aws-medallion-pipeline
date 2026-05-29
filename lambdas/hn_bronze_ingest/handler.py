"""
Bronze-layer ingest: fetch yesterday's Hacker News items via Algolia and write raw JSON to S3.
No transformation — full API page payloads are stored as-is.
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger()
logger.setLevel(logging.INFO)

ALGOLIA_BASE = "https://hn.algolia.com/api/v1/search_by_date"

# Algolia tag -> bronze folder name (spec terminology)
HN_TYPES: dict[str, str] = {
    "story": "story",
    "ask_hn": "ask",
    "comment": "comment",
    "job": "job",
    "poll": "poll",
}

MAX_RETRIES = 5
RETRY_BACKOFF_SEC = 2.0


def _env(name: str, default: str | None = None) -> str:
    value = os.environ.get(name, default)
    if value is None or value == "":
        raise ValueError(f"Missing required environment variable: {name}")
    return value


def _content_date(event: dict[str, Any] | None) -> date:
    """Previous UTC calendar day, or override via event / CONTENT_DATE env (YYYY-MM-DD)."""
    override = None
    if event and event.get("content_date"):
        override = event["content_date"]
    override = override or os.environ.get("CONTENT_DATE")
    if override:
        return date.fromisoformat(str(override))
    return (datetime.now(timezone.utc).date() - timedelta(days=1))


def _day_unix_range(d: date) -> tuple[int, int]:
    start = datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    return int(start.timestamp()), int(end.timestamp())


def _fetch_page(tag: str, start_ts: int, end_ts: int, page: int) -> dict[str, Any]:
    params = {
        "tags": tag,
        "numericFilters": f"created_at_i>={start_ts},created_at_i<{end_ts}",
        "hitsPerPage": "100",
        "page": str(page),
    }
    url = f"{ALGOLIA_BASE}?{urllib.parse.urlencode(params)}"
    last_error: Exception | None = None

    for attempt in range(MAX_RETRIES):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "aws-medallion-pipeline/1.0"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
            last_error = exc
            wait = RETRY_BACKOFF_SEC * (2**attempt)
            logger.warning("Algolia request failed (attempt %s/%s): %s", attempt + 1, MAX_RETRIES, exc)
            time.sleep(wait)

    raise RuntimeError(f"Algolia fetch failed for tag={tag} page={page}") from last_error


def _ingest_type(
    s3_client: Any,
    bucket: str,
    prefix: str,
    content_date: date,
    algolia_tag: str,
    folder: str,
    start_ts: int,
    end_ts: int,
) -> dict[str, Any]:
    date_str = content_date.isoformat()
    base_key = f"{prefix}/hackernews/content_date={date_str}/{folder}"
    page = 0
    total_hits = 0
    pages_written = 0

    while True:
        payload = _fetch_page(algolia_tag, start_ts, end_ts, page)
        hits = payload.get("hits", [])
        nb_pages = int(payload.get("nbPages", 0))

        key = f"{base_key}/page_{page:04d}.json"
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        s3_client.put_object(
            Bucket=bucket,
            Key=key,
            Body=body,
            ContentType="application/json",
        )
        pages_written += 1
        total_hits += len(hits)
        logger.info("Wrote s3://%s/%s (%s hits)", bucket, key, len(hits))

        page += 1
        if page >= nb_pages or not hits:
            break

    return {
        "algolia_tag": algolia_tag,
        "folder": folder,
        "pages_written": pages_written,
        "hit_count": total_hits,
    }


def lambda_handler(event: dict[str, Any] | None, context: Any) -> dict[str, Any]:
    event = event or {}
    bucket = _env("DATA_LAKE_BUCKET")
    prefix = os.environ.get("BRONZE_PREFIX", "bronze").strip("/")
    content_date = _content_date(event)
    start_ts, end_ts = _day_unix_range(content_date)

    logger.info(
        "Bronze HN ingest for content_date=%s (unix %s .. %s)",
        content_date.isoformat(),
        start_ts,
        end_ts,
    )

    import boto3

    s3 = boto3.client("s3")
    results: list[dict[str, Any]] = []

    for algolia_tag, folder in HN_TYPES.items():
        summary = _ingest_type(
            s3, bucket, prefix, content_date, algolia_tag, folder, start_ts, end_ts
        )
        results.append(summary)

    manifest_key = f"{prefix}/hackernews/content_date={content_date.isoformat()}/manifest.json"
    manifest = {
        "source": "hackernews",
        "api": "hn.algolia.com/api/v1/search_by_date",
        "content_date": content_date.isoformat(),
        "unix_range": {"start": start_ts, "end_exclusive": end_ts},
        "ingested_at": datetime.now(timezone.utc).isoformat(),
        "types": results,
    }
    s3.put_object(
        Bucket=bucket,
        Key=manifest_key,
        Body=json.dumps(manifest, indent=2).encode("utf-8"),
        ContentType="application/json",
    )

    return {"status": "ok", "content_date": content_date.isoformat(), "types": results}
