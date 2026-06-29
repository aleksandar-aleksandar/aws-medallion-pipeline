"""Gold layer constants and helpers."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

PLATFORM_HN = "Hacker News"
PLATFORM_X = "X"
PLATFORM_PARTITION_HN = "HackerNews"
PLATFORM_PARTITION_X = "X"

HN_POST_TYPES = ("story", "ask", "comment", "job", "poll")


def platform_partition(platform: str) -> str:
    return PLATFORM_PARTITION_HN if platform == PLATFORM_HN else PLATFORM_PARTITION_X


def metric_date_from_event(event: dict[str, Any] | None) -> date:
    from datetime import timedelta

    event = event or {}
    override = event.get("metric_date") or event.get("content_date") or event.get("METRIC_DATE")
    if override:
        return date.fromisoformat(str(override))
    return datetime.now(timezone.utc).date() - timedelta(days=1)


def iso_to_date(value: Any) -> date | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return None
    try:
        if "T" in text:
            return datetime.strptime(text[:10], "%Y-%m-%d").date()
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def date_str(d: date) -> str:
    return d.isoformat()
