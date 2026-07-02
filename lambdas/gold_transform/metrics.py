"""Compute gold metrics and KPIs from silver DataFrames."""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

import pandas as pd

from common import (
    HN_POST_TYPES,
    PLATFORM_HN,
    PLATFORM_PARTITION_HN,
    PLATFORM_PARTITION_X,
    PLATFORM_X,
    date_str,
    iso_to_date,
    platform_partition,
)
from karma import enrich_hn_karma

logger = logging.getLogger(__name__)


def _posts_on_date(posts_df: pd.DataFrame, metric_date: date) -> pd.DataFrame:
    if posts_df.empty:
        return posts_df
    df = posts_df.copy()
    df["post_date"] = df["created_at"].apply(iso_to_date)
    return df[df["post_date"] == metric_date]


def daily_hn_post_counts(posts_df: pd.DataFrame, metric_date: date) -> pd.DataFrame:
    day_posts = _posts_on_date(posts_df, metric_date)
    hn = day_posts[day_posts["platform"] == PLATFORM_HN]
    rows: list[dict[str, Any]] = []
    for post_type in HN_POST_TYPES:
        count = int((hn["post_type"] == post_type).sum())
        rows.append(
            {
                "date": date_str(metric_date),
                "post_type": post_type,
                "post_count": count,
            }
        )
    return pd.DataFrame(rows)


def daily_active_users(posts_df: pd.DataFrame, metric_date: date) -> pd.DataFrame:
    day_posts = _posts_on_date(posts_df, metric_date)
    rows: list[dict[str, Any]] = []
    for platform, partition in ((PLATFORM_HN, PLATFORM_PARTITION_HN), (PLATFORM_X, PLATFORM_PARTITION_X)):
        platform_posts = day_posts[day_posts["platform"] == platform]
        active = int(platform_posts["author_username"].nunique())
        rows.append(
            {
                "date": date_str(metric_date),
                "platform": platform,
                "platform_partition": partition,
                "active_users": active,
            }
        )
    return pd.DataFrame(rows)


def daily_users_metric(users_df: pd.DataFrame, posts_df: pd.DataFrame, metric_date: date) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for platform, partition in ((PLATFORM_HN, PLATFORM_PARTITION_HN), (PLATFORM_X, PLATFORM_PARTITION_X)):
        platform_users = users_df[users_df["platform"] == platform].copy()
        total_users = int(platform_users["username"].nunique())

        platform_users["user_created_date"] = platform_users["created_at"].apply(iso_to_date)
        new_from_profile = platform_users[platform_users["user_created_date"] == metric_date]

        if posts_df.empty:
            new_users = int(new_from_profile["username"].nunique())
        else:
            day_posts = _posts_on_date(posts_df, metric_date)
            first_post_dates = (
                posts_df[posts_df["platform"] == platform]
                .assign(post_date=lambda d: d["created_at"].apply(iso_to_date))
                .groupby("author_username")["post_date"]
                .min()
            )
            new_from_activity = set(
                first_post_dates[first_post_dates == metric_date].index.astype(str).tolist()
            )
            new_users = len(
                set(new_from_profile["username"].astype(str).tolist()) | new_from_activity
            )

        rows.append(
            {
                "date": date_str(metric_date),
                "platform": platform,
                "platform_partition": partition,
                "total_users": total_users,
                "new_users": new_users,
            }
        )
    return pd.DataFrame(rows)


def top_x_users_by_followers(users_df: pd.DataFrame, metric_date: date, limit: int = 10) -> pd.DataFrame:
    x_users = users_df[users_df["platform"] == PLATFORM_X].copy()
    x_users["follower_count"] = pd.to_numeric(x_users["follower_count"], errors="coerce")
    x_users = x_users.dropna(subset=["follower_count"]).sort_values("follower_count", ascending=False)
    top = x_users.drop_duplicates(subset=["username"]).head(limit).copy()
    top["date"] = date_str(metric_date)
    top["rank"] = range(1, len(top) + 1)
    return top[
        ["date", "rank", "username", "follower_count", "is_verified", "platform"]
    ]


def top_hn_users_by_karma(
    users_df: pd.DataFrame,
    posts_df: pd.DataFrame,
    metric_date: date,
    *,
    ascending: bool,
    limit: int = 10,
) -> pd.DataFrame:
    day_posts = _posts_on_date(posts_df, metric_date)
    active_authors = day_posts[day_posts["platform"] == PLATFORM_HN]["author_username"].dropna().unique().tolist()
    enriched = enrich_hn_karma(users_df, posts_df, active_usernames=[str(a) for a in active_authors])

    hn_active = enriched[
        (enriched["platform"] == PLATFORM_HN) & (enriched["username"].isin(active_authors))
    ].copy()
    hn_active["karma_score"] = pd.to_numeric(hn_active["karma_score"], errors="coerce").astype("float64")
    hn_active = hn_active.dropna(subset=["karma_score"]).sort_values("karma_score", ascending=ascending)
    top = hn_active.drop_duplicates(subset=["username"]).head(limit).copy()
    top["date"] = date_str(metric_date)
    top["rank"] = range(1, len(top) + 1)
    direction = "lowest" if ascending else "highest"
    top["ranking"] = direction
    return top[["date", "rank", "ranking", "username", "karma_score", "platform"]]


def top_hn_jobs_by_score(posts_df: pd.DataFrame, metric_date: date, limit: int = 10) -> pd.DataFrame:
    day_posts = _posts_on_date(posts_df, metric_date)
    jobs = day_posts[(day_posts["platform"] == PLATFORM_HN) & (day_posts["post_type"] == "job")].copy()
    if jobs.empty:
        return jobs
    # HN job hits often lack points in Algolia bronze; default to 0 so jobs still rank.
    jobs["points"] = pd.to_numeric(jobs["points"], errors="coerce").fillna(0).astype(int)
    jobs = jobs.sort_values(["points", "post_id"], ascending=[False, True]).head(limit)
    jobs["date"] = date_str(metric_date)
    jobs["rank"] = range(1, len(jobs) + 1)
    return jobs[
        ["date", "rank", "post_id", "author_username", "content_text", "points", "created_at", "platform"]
    ]


def top_hn_posts_by_score(posts_df: pd.DataFrame, metric_date: date, limit: int = 10) -> pd.DataFrame:
    day_posts = _posts_on_date(posts_df, metric_date)
    stories = day_posts[
        (day_posts["platform"] == PLATFORM_HN) & (day_posts["post_type"].isin(["story", "ask", "poll"]))
    ].copy()
    stories["points"] = pd.to_numeric(stories["points"], errors="coerce")
    stories = stories.dropna(subset=["points"]).sort_values("points", ascending=False).head(limit)
    stories["date"] = date_str(metric_date)
    stories["rank"] = range(1, len(stories) + 1)
    return stories[
        [
            "date",
            "rank",
            "post_id",
            "post_type",
            "author_username",
            "content_text",
            "points",
            "created_at",
            "platform",
        ]
    ]


def data_quality_score(users_df: pd.DataFrame, posts_df: pd.DataFrame, metric_date: date) -> pd.DataFrame:
    frames = [
        ("users", users_df),
        ("posts", posts_df),
    ]
    rows: list[dict[str, Any]] = []
    for table_name, frame in frames:
        if frame.empty:
            rows.append(
                {
                    "date": date_str(metric_date),
                    "table_name": table_name,
                    "total_cells": 0,
                    "non_null_cells": 0,
                    "quality_score_pct": 0.0,
                }
            )
            continue
        total_cells = int(frame.size)
        non_null_cells = int(frame.notna().sum().sum())
        pct = round((non_null_cells / total_cells) * 100.0, 2) if total_cells else 0.0
        rows.append(
            {
                "date": date_str(metric_date),
                "table_name": table_name,
                "total_cells": total_cells,
                "non_null_cells": non_null_cells,
                "quality_score_pct": pct,
            }
        )

    overall_total = sum(r["total_cells"] for r in rows)
    overall_non_null = sum(r["non_null_cells"] for r in rows)
    overall_pct = round((overall_non_null / overall_total) * 100.0, 2) if overall_total else 0.0
    rows.append(
        {
            "date": date_str(metric_date),
            "table_name": "overall",
            "total_cells": overall_total,
            "non_null_cells": overall_non_null,
            "quality_score_pct": overall_pct,
        }
    )
    return pd.DataFrame(rows)


def compute_all_metrics(
    users_df: pd.DataFrame,
    posts_df: pd.DataFrame,
    metric_date: date,
) -> dict[str, pd.DataFrame]:
    logger.info("Computing gold metrics for %s", metric_date.isoformat())
    return {
        "daily_hn_post_counts": daily_hn_post_counts(posts_df, metric_date),
        "daily_active_users": daily_active_users(posts_df, metric_date),
        "daily_users_metric": daily_users_metric(users_df, posts_df, metric_date),
        "top_x_users_by_followers": top_x_users_by_followers(users_df, metric_date),
        "top_hn_users_by_karma_high": top_hn_users_by_karma(
            users_df, posts_df, metric_date, ascending=False
        ),
        "top_hn_users_by_karma_low": top_hn_users_by_karma(
            users_df, posts_df, metric_date, ascending=True
        ),
        "top_hn_jobs_by_score": top_hn_jobs_by_score(posts_df, metric_date),
        "top_hn_posts_by_score": top_hn_posts_by_score(posts_df, metric_date),
        "data_quality_score": data_quality_score(users_df, posts_df, metric_date),
    }
