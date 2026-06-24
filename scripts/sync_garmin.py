#!/usr/bin/env python3
"""Sync Garmin wellness, lifestyle, and activities; merge with Strava."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.db.connection import init_db
from src.sync.garmin_sync import sync_garmin
from src.sync.merge import merge_strava_garmin


def main() -> None:
    init_db()
    print("Starting Garmin sync...")
    stats = sync_garmin()
    print(
        f"  {stats['days']} days processed, "
        f"{stats['wellness_rows']} wellness, "
        f"{stats['lifestyle_rows']} lifestyle, "
        f"{stats['garmin_activities']} activities, "
        f"{stats['errors']} errors"
    )

    print("Merging Garmin activities with Strava...")
    merge_stats = merge_strava_garmin()
    print(
        f"  {merge_stats['matched']} newly matched, "
        f"{merge_stats['already_matched']} already matched, "
        f"{merge_stats['unmatched_garmin']} unmatched Garmin-only"
    )


if __name__ == "__main__":
    main()
