#!/usr/bin/env python3
"""Local smoke test for HN Algolia bronze queries (no AWS)."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lambdas" / "hn_bronze_ingest"))

from handler import ALGOLIA_BASE, HN_TYPES, _day_unix_range, _fetch_page  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Test HN Algolia fetch for one day/type")
    parser.add_argument("--date", help="Content date YYYY-MM-DD (default: yesterday UTC)")
    parser.add_argument("--tag", default="story", help=f"Algolia tag (default story). All: {list(HN_TYPES)}")
    args = parser.parse_args()

    content_date = (
        date.fromisoformat(args.date)
        if args.date
        else datetime.now(timezone.utc).date() - timedelta(days=1)
    )
    start_ts, end_ts = _day_unix_range(content_date)
    print(f"content_date={content_date}  unix [{start_ts}, {end_ts})")

    tags = HN_TYPES if args.tag == "all" else {args.tag: HN_TYPES.get(args.tag, args.tag)}
    if args.tag != "all" and args.tag not in HN_TYPES:
        print(f"Warning: unknown tag {args.tag!r}, using as Algolia tag directly")

    for algolia_tag in tags:
        payload = _fetch_page(algolia_tag, start_ts, end_ts, 0)
        hits = payload.get("hits", [])
        print(
            f"  {algolia_tag}: nbHits={payload.get('nbHits')} "
            f"nbPages={payload.get('nbPages')} first_page_hits={len(hits)}"
        )
        if hits:
            sample = hits[0]
            print(f"    sample keys: {sorted(sample.keys())[:8]}...")


if __name__ == "__main__":
    main()
