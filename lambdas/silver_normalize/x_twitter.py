"""Normalize X (Twitter) bronze CSV datasets into users and posts rows."""

from __future__ import annotations

import io
from typing import Any, Callable, Iterable

import pandas as pd

from common import (
    PLATFORM_X,
    dedupe_posts,
    dedupe_users,
    normalize_iso_timestamp,
    strip_html,
    user_id,
    x_post_id,
)

# Column sets we accept (bitcoin-style tweet CSVs).
TWEET_CSV_COLUMNS = {
    "user_name",
    "user_created",
    "user_followers",
    "user_verified",
    "date",
    "text",
    "is_retweet",
}


def _parse_bool(value: str | None) -> bool | None:
    if value is None or value == "":
        return None
    lowered = str(value).strip().lower()
    if lowered in {"true", "1", "yes"}:
        return True
    if lowered in {"false", "0", "no"}:
        return False
    return None


def _safe_int(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return None


def is_tweet_csv(fieldnames: list[str] | None) -> bool:
    if not fieldnames:
        return False
    cols = {c.strip() for c in fieldnames}
    return TWEET_CSV_COLUMNS.issubset(cols)


def _cell_str(value: Any) -> str:
    if value is None:
        return ""
    try:
        import pandas as pd

        if isinstance(value, float) and pd.isna(value):
            return ""
    except ImportError:
        pass
    text = str(value).strip()
    return "" if text.lower() == "nan" else text


def csv_text_to_rows(csv_text: str, dataset_name: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Parse one bronze X CSV payload into users and posts."""
    try:
        frame = pd.read_csv(
            io.StringIO(csv_text),
            engine="python",
            on_bad_lines="skip",
        )
    except Exception:
        return [], []

    if not is_tweet_csv([str(c) for c in frame.columns]):
        return [], []

    users: list[dict[str, Any]] = []
    posts: list[dict[str, Any]] = []

    for row in frame.to_dict(orient="records"):
        username = _cell_str(row.get("user_name"))
        text = strip_html(_cell_str(row.get("text")))
        if not username or not text:
            continue

        user_created = normalize_iso_timestamp(_cell_str(row.get("user_created")))
        post_created = normalize_iso_timestamp(_cell_str(row.get("date")))
        is_retweet = _parse_bool(_cell_str(row.get("is_retweet")))
        post_type = "retweet" if is_retweet else "tweet"
        post_id = x_post_id(username, post_created or "", text)

        users.append(
            {
                "user_id": user_id(PLATFORM_X, username),
                "username": username,
                "platform": PLATFORM_X,
                "karma_score": None,
                "follower_count": _safe_int(_cell_str(row.get("user_followers"))),
                "is_verified": _parse_bool(_cell_str(row.get("user_verified"))),
                "created_at": user_created,
            }
        )
        posts.append(
            {
                "post_id": post_id,
                "author_username": username,
                "content_text": text,
                "created_at": post_created,
                "post_type": post_type,
                "platform": PLATFORM_X,
                "parent_id": None,
                "story_id": None,
                "child_ids": None,
                "points": None,
                "source_dataset": dataset_name,
            }
        )

    return dedupe_users(users), dedupe_posts(posts)


def normalize_x_bronze_keys(
    object_keys: Iterable[str],
    *,
    read_text: Callable[[str], str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    users: list[dict[str, Any]] = []
    posts: list[dict[str, Any]] = []

    for key in object_keys:
        if "/bronze/x/" not in key and not key.startswith("bronze/x/"):
            continue
        if not key.endswith(".csv"):
            continue

        # bronze/x/dataset=<name>/raw/<file>.csv
        dataset_name = "unknown"
        parts = key.split("/")
        for part in parts:
            if part.startswith("dataset="):
                dataset_name = part.split("=", 1)[1]
                break

        csv_text = read_text(key)
        page_users, page_posts = csv_text_to_rows(csv_text, dataset_name)
        users.extend(page_users)
        posts.extend(page_posts)

    return dedupe_users(users), dedupe_posts(posts)
