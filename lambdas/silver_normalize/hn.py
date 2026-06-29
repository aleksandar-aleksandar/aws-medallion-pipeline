"""Normalize Hacker News bronze JSON pages into users and posts rows."""

from __future__ import annotations

import json
from typing import Any, Callable, Iterable

from common import (
    PLATFORM_HN,
    dedupe_posts,
    dedupe_users,
    parse_hn_timestamp,
    strip_html,
    user_id,
)

# Bronze folder name -> silver post_type
HN_FOLDER_TO_TYPE: dict[str, str] = {
    "story": "story",
    "ask": "ask",
    "comment": "comment",
    "job": "job",
    "poll": "poll",
}


def _content_text(hit: dict[str, Any], post_type: str) -> str:
    if post_type == "comment":
        return strip_html(hit.get("comment_text") or hit.get("text") or "")
    title = strip_html(hit.get("title") or "")
    url = (hit.get("url") or "").strip()
    if url and post_type in {"story", "job", "ask"}:
        return f"{title} {url}".strip() if title else url
    return title


def hit_to_rows(hit: dict[str, Any], post_type: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Map one Algolia hit to (user_row, post_row)."""
    author = (hit.get("author") or "").strip()
    if not author:
        return None, None

    post_id = str(hit.get("objectID") or hit.get("story_id") or "").strip()
    if not post_id:
        return None, None

    created_at = parse_hn_timestamp(hit)
    content = _content_text(hit, post_type)
    if not content and post_type != "comment":
        return None, None

    user_row = {
        "user_id": user_id(PLATFORM_HN, author),
        "username": author,
        "platform": PLATFORM_HN,
        "karma_score": None,
        "follower_count": None,
        "is_verified": None,
        "created_at": created_at,
    }
    post_row = {
        "post_id": post_id,
        "author_username": author,
        "content_text": content,
        "created_at": created_at,
        "post_type": post_type,
        "platform": PLATFORM_HN,
        # Flatten nested HN references (kids/children/parts are comment/poll ids).
        "parent_id": str(hit["parent_id"]) if hit.get("parent_id") is not None else None,
        "story_id": str(hit["story_id"]) if hit.get("story_id") is not None else None,
        "child_ids": _flatten_id_list(hit.get("kids") or hit.get("children") or hit.get("parts")),
        "points": _safe_int(hit.get("points")),
    }
    return user_row, post_row


def _flatten_id_list(values: Any) -> str | None:
    if not values:
        return None
    if isinstance(values, list):
        return ",".join(str(v) for v in values)
    return str(values)


def _safe_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def parse_hn_page(payload: dict[str, Any], post_type: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    users: list[dict[str, Any]] = []
    posts: list[dict[str, Any]] = []
    for hit in payload.get("hits", []):
        user_row, post_row = hit_to_rows(hit, post_type)
        if user_row:
            users.append(user_row)
        if post_row:
            posts.append(post_row)
    return users, posts


def normalize_hn_bronze_keys(
    object_keys: Iterable[str],
    *,
    read_json: Callable[[str], dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Read bronze HN page JSON objects and return deduplicated users/posts lists.

    read_json(key) -> dict payload
    """
    users: list[dict[str, Any]] = []
    posts: list[dict[str, Any]] = []

    for key in object_keys:
        parts = key.split("/")
        try:
            hn_idx = parts.index("hackernews")
            folder = parts[hn_idx + 2]
        except (ValueError, IndexError):
            continue
        if not key.endswith(".json") or key.endswith("manifest.json"):
            continue

        post_type = HN_FOLDER_TO_TYPE.get(folder)
        if not post_type:
            continue

        payload = read_json(key)
        page_users, page_posts = parse_hn_page(payload, post_type)
        users.extend(page_users)
        posts.extend(page_posts)

    return dedupe_users(users), dedupe_posts(posts)
