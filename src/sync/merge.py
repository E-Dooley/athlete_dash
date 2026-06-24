"""Match Garmin activities to Strava rows and attach source metadata."""

from __future__ import annotations

from datetime import datetime

import duckdb

from src.db.connection import get_connection

MATCH_TOLERANCE_SECONDS = 300  # 5 minutes
DISTANCE_TOLERANCE = 0.05  # 5%


def merge_strava_garmin(conn: duckdb.DuckDBPyConnection | None = None) -> dict[str, int]:
    """
    Link Strava runs to Garmin activities by start time and distance.
    Updates activities.garmin_activity_id and garmin_activities.matched_strava_id.
    """
    own_conn = conn is None
    if own_conn:
        conn = get_connection()

    stats = {"matched": 0, "already_matched": 0, "unmatched_garmin": 0}

    try:
        strava_runs = conn.execute(
            """
            SELECT strava_id, start_date, distance_meters, garmin_activity_id
            FROM activities
            WHERE category = 'run' AND hidden = FALSE
            ORDER BY start_date
            """
        ).fetchall()

        garmin_rows = conn.execute(
            """
            SELECT garmin_id, start_date, distance_meters, matched_strava_id
            FROM garmin_activities
            ORDER BY start_date
            """
        ).fetchall()

        used_garmin: set[int] = set()

        for strava_id, s_start, s_dist, existing_garmin in strava_runs:
            if existing_garmin:
                stats["already_matched"] += 1
                used_garmin.add(int(existing_garmin))
                continue

            best_id = None
            best_delta = MATCH_TOLERANCE_SECONDS + 1

            for garmin_id, g_start, g_dist, matched in garmin_rows:
                if garmin_id in used_garmin or matched:
                    continue
                if s_start is None or g_start is None:
                    continue

                delta = abs((s_start - g_start).total_seconds())
                if delta > MATCH_TOLERANCE_SECONDS:
                    continue

                if s_dist and g_dist:
                    ref = max(s_dist, g_dist, 1)
                    if abs(s_dist - g_dist) / ref > DISTANCE_TOLERANCE:
                        continue

                if delta < best_delta:
                    best_delta = delta
                    best_id = garmin_id

            if best_id is not None:
                conn.execute(
                    "UPDATE activities SET garmin_activity_id = ?, source = 'both' WHERE strava_id = ?",
                    [best_id, strava_id],
                )
                conn.execute(
                    "UPDATE garmin_activities SET matched_strava_id = ? WHERE garmin_id = ?",
                    [strava_id, best_id],
                )
                used_garmin.add(best_id)
                stats["matched"] += 1

        stats["unmatched_garmin"] = conn.execute(
            "SELECT COUNT(*) FROM garmin_activities WHERE matched_strava_id IS NULL"
        ).fetchone()[0]

        conn.execute(
            """
            INSERT INTO sync_metadata (key, value, updated_at)
            VALUES ('garmin_last_merge_at', ?, ?)
            ON CONFLICT (key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
            """,
            [datetime.now().isoformat(), datetime.now()],
        )
    finally:
        if own_conn:
            conn.close()

    return stats
