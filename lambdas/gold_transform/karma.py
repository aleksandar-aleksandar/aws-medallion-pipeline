"""Fetch Hacker News user karma from the public Firebase API."""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

logger = logging.getLogger(__name__)

HN_USER_API = "https://hacker-news.firebaseio.com/v0/user/{username}.json"
MAX_WORKERS = 16
REQUEST_TIMEOUT = 10


def fetch_karma(username: str) -> int | None:
    url = HN_USER_API.format(username=username)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "aws-medallion-pipeline/1.0"})
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        if not payload:
            return None
        karma = payload.get("karma")
        return int(karma) if karma is not None else None
    except (urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
        logger.debug("karma fetch failed for %s: %s", username, exc)
        return None


def fetch_karma_batch(usernames: list[str]) -> dict[str, int | None]:
    """Fetch karma for many usernames concurrently."""
    unique = sorted({u.strip() for u in usernames if u and u.strip()})
    results: dict[str, int | None] = {}
    if not unique:
        return results

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(fetch_karma, name): name for name in unique}
        for future in as_completed(futures):
            name = futures[future]
            try:
                results[name] = future.result()
            except Exception as exc:  # noqa: BLE001
                logger.warning("karma worker error for %s: %s", name, exc)
                results[name] = None
            time.sleep(0.02)

    return results


def enrich_hn_karma(
    users_df: Any,
    posts_df: Any,
    *,
    active_usernames: list[str] | None = None,
) -> Any:
    """
    Fill missing HN karma_score using Firebase API, then max post points as fallback.
    Returns users_df with karma_score updated (pandas DataFrame).
    """
    import pandas as pd

    if users_df.empty:
        return users_df

    df = users_df.copy()
    hn_mask = df["platform"] == "Hacker News"
    if not hn_mask.any():
        return df

    usernames = active_usernames
    if usernames is None:
        usernames = df.loc[hn_mask, "username"].dropna().astype(str).tolist()

    karma_map = fetch_karma_batch(usernames)

    if not posts_df.empty:
        hn_posts = posts_df[posts_df["platform"] == "Hacker News"].copy()
        hn_posts["points_num"] = pd.to_numeric(hn_posts.get("points"), errors="coerce")
        fallback = (
            hn_posts.groupby("author_username", dropna=True)["points_num"]
            .max()
            .dropna()
            .astype(int)
            .to_dict()
        )
    else:
        fallback = {}

    def resolve_karma(row: Any) -> Any:
        if row["platform"] != "Hacker News":
            return row.get("karma_score")
        if pd.notna(row.get("karma_score")):
            return row["karma_score"]
        name = str(row["username"])
        api_karma = karma_map.get(name)
        if api_karma is not None:
            return api_karma
        return fallback.get(name)

    df.loc[hn_mask, "karma_score"] = df.loc[hn_mask].apply(resolve_karma, axis=1)
    return df
