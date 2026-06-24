#!/usr/bin/env python3
"""Sync Strava and Garmin data sources."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.db.connection import init_db
from src.sync.garmin_sync import sync_garmin
from src.sync.merge import merge_strava_garmin
from src.sync.strava_sync import sync_strava


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync Strava + Garmin into DuckDB")
    parser.add_argument("--strava-only", action="store_true")
    parser.add_argument("--garmin-only", action="store_true")
    parser.add_argument("--strava-limit", type=int, default=None)
    args = parser.parse_args()

    init_db()

    if not args.garmin_only:
        print("=== Strava ===")
        result = sync_strava(limit=args.strava_limit)
        print(
            f"Upserted {result['upserted']}, skipped {result['skipped']}, "
            f"errors {result['errors']}"
        )

    if not args.strava_only:
        print("=== Garmin ===")
        gstats = sync_garmin()
        print(
            f"{gstats['wellness_rows']} wellness days, "
            f"{gstats['lifestyle_rows']} lifestyle days, "
            f"{gstats['garmin_activities']} activities"
        )
        merge = merge_strava_garmin()
        print(f"Matched {merge['matched']} Strava runs to Garmin")


if __name__ == "__main__":
    main()
