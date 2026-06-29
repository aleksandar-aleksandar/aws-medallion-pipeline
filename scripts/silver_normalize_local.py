#!/usr/bin/env python3
"""Run silver normalization locally (filesystem or live S3)."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAMBDA_DIR = ROOT / "lambdas" / "silver_normalize"
sys.path.insert(0, str(LAMBDA_DIR))

from normalize import (  # noqa: E402
    _prepare_posts_df,
    _prepare_users_df,
    content_date_from_event,
    list_s3_keys,
    read_s3_json,
    read_s3_text,
    run_silver_normalize,
    write_silver_parquet,
)
from hn import normalize_hn_bronze_keys  # noqa: E402
from x_twitter import normalize_x_bronze_keys  # noqa: E402
from common import dedupe_posts, dedupe_users  # noqa: E402


def _run_local(bronze_root: Path, content_date: date, output_dir: Path, process_x: bool) -> dict:
    hn_dir = bronze_root / "hackernews" / f"content_date={content_date.isoformat()}"
    if not hn_dir.is_dir():
        raise FileNotFoundError(f"HN bronze folder not found: {hn_dir}")

    keys: list[str] = []
    for path in sorted(hn_dir.rglob("page_*.json")):
        rel = path.relative_to(bronze_root).as_posix()
        keys.append(rel)

    def read_json(key: str) -> dict:
        return json.loads((bronze_root / key).read_text(encoding="utf-8"))

    hn_users, hn_posts = normalize_hn_bronze_keys(keys, read_json=read_json)

    x_users, x_posts = [], []
    if process_x:
        x_root = bronze_root / "x"
        x_keys: list[str] = []
        if x_root.is_dir():
            for path in sorted(x_root.rglob("*.csv")):
                x_keys.append(path.relative_to(bronze_root).as_posix())
        x_users, x_posts = normalize_x_bronze_keys(
            x_keys,
            read_text=lambda key: (bronze_root / key).read_text(encoding="utf-8", errors="replace"),
        )

    users = dedupe_users(hn_users + x_users)
    posts = dedupe_posts(hn_posts + x_posts)
    users_df = _prepare_users_df(users)
    posts_df = _prepare_posts_df(posts)

    output_dir.mkdir(parents=True, exist_ok=True)
    users_df.to_parquet(output_dir / "users.parquet", index=False)
    posts_df.to_parquet(output_dir / "posts.parquet", index=False)

    return {
        "mode": "local",
        "content_date": content_date.isoformat(),
        "users": len(users),
        "posts": len(posts),
        "output_dir": str(output_dir),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Silver normalize (local dir or S3)")
    parser.add_argument("--date", help="Content date YYYY-MM-DD (default: yesterday UTC)")
    parser.add_argument("--bronze-root", type=Path, help="Local bronze folder (e.g. data/bronze)")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data" / "silver" / "out")
    parser.add_argument("--s3", action="store_true", help="Read/write via AWS S3 (needs credentials)")
    parser.add_argument("--bucket", help="S3 bucket (default: terraform output)")
    parser.add_argument("--no-x", action="store_true", help="Skip X datasets")
    args = parser.parse_args()

    event: dict = {}
    if args.date:
        event["content_date"] = args.date
    content_date = content_date_from_event(event)
    process_x = not args.no_x

    if args.s3:
        import boto3

        bucket = args.bucket
        if not bucket:
            raise SystemExit("Pass --bucket or set via terraform output for --s3 mode")

        s3 = boto3.client("s3")
        result = run_silver_normalize(
            s3_client=s3,
            bucket=bucket,
            bronze_prefix="bronze",
            silver_prefix="silver",
            content_date=content_date,
            process_x=process_x,
        )
        print(json.dumps(result, indent=2))
        return

    if not args.bronze_root:
        raise SystemExit("Use --bronze-root for local mode or --s3 for AWS mode")

    result = _run_local(args.bronze_root, content_date, args.output_dir, process_x)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
