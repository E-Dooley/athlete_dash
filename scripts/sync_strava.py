#!/usr/bin/env python3
"""Sync Strava activities into the local DuckDB store."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import parse_sync_windows
from src.db.connection import init_db
from src.sync.strava_sync import sync_strava


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync Strava activities to DuckDB")
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Re-fetch activities even if already in the database",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max number of activity detail fetches this run (useful when rate-limited)",
    )
    args = parser.parse_args()

    init_db()
    windows = parse_sync_windows()
    labels = ", ".join(w["label"] for w in windows)
    print(f"Starting Strava sync for: {labels}")
    if args.limit:
        print(f"Limit: {args.limit} detail fetches this run")

    result = sync_strava(refresh=args.refresh, limit=args.limit)

    for window in result["windows"]:
        print(
            f"  {window['label']}: listed {window['listed']}, "
            f"upserted {window['upserted']}, skipped {window['skipped']}, "
            f"errors {window['errors']}"
        )
    print(
        f"Done. Total upserted {result['upserted']}, "
        f"skipped {result['skipped']}, errors {result['errors']}."
    )


if __name__ == "__main__":
    main()
