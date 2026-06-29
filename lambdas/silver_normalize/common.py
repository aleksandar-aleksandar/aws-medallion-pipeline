"""Shared silver-layer helpers: timestamps, HTML cleanup, IDs, deduplication."""

from __future__ import annotations

import hashlib
import math
import re
import uuid
from datetime import datetime, timezone
from html import unescape
from typing import Any

PLATFORM_HN = "Hacker News"
PLATFORM_X = "X"

# S3 partition folder values (spec layout uses HackerNews without a space).
PLATFORM_PARTITION_HN = "HackerNews"
PLATFORM_PARTITION_X = "X"

_HTML_TAG_RE = re.compile(r"<[^>]+>")


def user_id(platform: str, username: str) -> str:
    """Deterministic UUID for a platform username (stable across runs)."""
    key = f"{platform}:{username}".lower()
    return str(uuid.uuid5(uuid.NAMESPACE_URL, key))


def x_post_id(username: str, created_at: str, text: str) -> str:
    """Synthetic post id when the bronze X dataset has no tweet id column."""
    digest = hashlib.sha256(f"{username}|{created_at}|{text}".encode("utf-8")).hexdigest()
    return digest[:32]


def strip_html(value: str | None) -> str:
    if not value:
        return ""
    text = unescape(value)
    text = _HTML_TAG_RE.sub("", text)
    return re.sub(r"\s+", " ", text).strip()


def parse_hn_timestamp(hit: dict[str, Any]) -> str | None:
    """HN Algolia hit -> UTC ISO-8601 string."""
    if hit.get("created_at_i") is not None:
        try:
            ts = int(hit["created_at_i"])
            return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        except (TypeError, ValueError):
            pass
    raw = hit.get("created_at")
    if isinstance(raw, str) and raw:
        return normalize_iso_timestamp(raw)
    return None


def normalize_iso_timestamp(value: str) -> str | None:
    """Normalize assorted timestamp strings to UTC ISO-8601."""
    value = value.strip()
    if not value:
        return None

    formats = (
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    )
    for fmt in formats:
        try:
            dt = datetime.strptime(value, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            else:
                dt = dt.astimezone(timezone.utc)
            return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            continue

    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return None


def partition_date_parts(iso_ts: Any) -> dict[str, str]:
    """Derive year/month/day partition columns from an ISO timestamp."""
    if iso_ts is None:
        return {"year": "unknown", "month": "unknown", "day": "unknown"}
    if isinstance(iso_ts, float) and math.isnan(iso_ts):
        return {"year": "unknown", "month": "unknown", "day": "unknown"}
    text = str(iso_ts).strip()
    if not text or text.lower() == "nan":
        return {"year": "unknown", "month": "unknown", "day": "unknown"}
    try:
        dt = datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return {"year": "unknown", "month": "unknown", "day": "unknown"}
    return {
        "year": f"{dt.year:04d}",
        "month": f"{dt.month:02d}",
        "day": f"{dt.day:02d}",
    }


def dedupe_users(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep the latest row per (platform, username)."""
    by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        key = (row["platform"], row["username"])
        existing = by_key.get(key)
        if existing is None:
            by_key[key] = row
            continue
        if (row.get("created_at") or "") >= (existing.get("created_at") or ""):
            by_key[key] = row
    return list(by_key.values())


def dedupe_posts(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep one row per (platform, post_id)."""
    by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        key = (row["platform"], row["post_id"])
        by_key[key] = row
    return list(by_key.values())
