#!/usr/bin/env python3
"""Diagnose Strava OAuth scopes and private_note API access (no secrets printed)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.db.connection import get_connection
from src.sync.strava_client import get_strava_client


def main() -> None:
    client = get_strava_client()

    # stravalib stores last token response on client after refresh in some versions;
    # also re-fetch via explicit refresh to inspect scope field only.
    import os
    from dotenv import load_dotenv

    load_dotenv()
    res = client.refresh_access_token(
        client_id=os.getenv("STRAVA_CLIENT_ID"),
        client_secret=os.getenv("STRAVA_CLIENT_SECRET"),
        refresh_token=os.getenv("STRAVA_REFRESH_TOKEN"),
    )
    scopes = res.get("scope") or res.get("scopes") or "(not returned on refresh)"
    print("Granted scopes:", scopes)
    has_read_all = "activity:read_all" in str(scopes)
    print("activity:read_all in refresh response:", has_read_all, "(often not returned on refresh)")

    conn = get_connection()
    row = conn.execute(
        """
        SELECT strava_id, name FROM activities
        WHERE description IS NOT NULL AND length(description) > 0
        ORDER BY start_date DESC LIMIT 1
        """
    ).fetchone()
    db_private = conn.execute(
        "SELECT COUNT(*) FROM activities WHERE private_note IS NOT NULL AND length(private_note) > 0"
    ).fetchone()[0]
    db_synced = conn.execute(
        "SELECT COUNT(*) FROM activities WHERE detail_synced = TRUE"
    ).fetchone()[0]
    conn.close()

    print(f"DB: {db_private} activities with private_note, {db_synced} with detail_synced=TRUE")

    if not row:
        print("No activities with descriptions in DB to test.")
        return

    activity_id, name = row
    print(f"Testing API activity {activity_id}: {name}")
    activity = client.get_activity(activity_id)
    desc = getattr(activity, "description", None) or ""
    private_note = getattr(activity, "private_note", None) or ""
    print(f"API description length: {len(desc)}")
    print(f"API private_note length: {len(private_note)}")

    if len(private_note) > 0:
        print("\nOAuth is working — API returned private_note data.")
    if db_synced == 0 and len(private_note) > 0:
        print("Action: Backfill DB — run: uv run python scripts/sync_strava.py --limit 5")
        print("  (repeat every ~15 min until all activities show detail_synced)")
    elif len(private_note) == 0 and len(desc) > 0:
        print(
            "\nAPI returned description but empty private_note. "
            "Re-authorize with activity:read_all: uv run python auth_setup.py"
        )


if __name__ == "__main__":
    main()
