"""Bulk Strava activity sync into DuckDB."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

import duckdb
from stravalib.client import Client

from src.config import category_for_type, is_workout, load_settings, parse_sync_windows
from src.db.connection import get_connection
from src.sync.strava_client import get_strava_client

METERS_PER_MILE = 1609.344
GEAR_CACHE: dict[int, str] = {}
RATE_LIMIT_SLEEP_SECONDS = 120
MAX_RETRIES = 5


def _request_delay() -> float:
    return float(load_settings().get("sync", {}).get("request_delay_seconds", 1.5))


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    if hasattr(value, "num"):
        return float(value.num)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> int | None:
    if value is None:
        return None
    if hasattr(value, "total_seconds"):
        return int(value.total_seconds())
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _enum_root(value: Any) -> str | None:
    if value is None:
        return None
    return getattr(value, "root", str(value))


def _primary_sport_type(activity: Any) -> str:
    """Prefer granular sport_type (e.g. PhysicalTherapy) over legacy type (e.g. Workout)."""
    sport = _enum_root(getattr(activity, "sport_type", None))
    if sport:
        return sport
    return _activity_type_name(activity)


def _resolve_gear_name(client: Client, gear_id: int | None) -> str | None:
    if gear_id is None:
        return None
    if gear_id in GEAR_CACHE:
        return GEAR_CACHE[gear_id]
    try:
        gear = client.get_gear(gear_id)
        name = getattr(gear, "name", None) or str(gear_id)
        GEAR_CACHE[gear_id] = name
        return name
    except Exception:
        return None


def _upsert_gear(conn: duckdb.DuckDBPyConnection, client: Client, gear_id: int) -> None:
    try:
        gear = client.get_gear(gear_id)
        synced_at = datetime.now()
        conn.execute(
            """
            INSERT INTO gear (gear_id, name, brand_name, distance_meters, synced_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (gear_id) DO UPDATE SET
                name = excluded.name,
                brand_name = excluded.brand_name,
                distance_meters = excluded.distance_meters,
                synced_at = excluded.synced_at
            """,
            [
                gear_id,
                getattr(gear, "name", None),
                getattr(gear, "brand_name", None),
                _safe_float(getattr(gear, "distance", None)),
                synced_at,
            ],
        )
        GEAR_CACHE[gear_id] = getattr(gear, "name", None) or str(gear_id)
    except Exception:
        pass


def activity_to_row(client: Client, activity: Any) -> dict[str, Any]:
    """Convert a full Strava activity into a DB row dict."""
    activity_type = _primary_sport_type(activity)
    start = activity.start_date
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    else:
        start = start.astimezone(timezone.utc)

    description = getattr(activity, "description", None) or ""
    private_note = getattr(activity, "private_note", None) or ""
    name = getattr(activity, "name", None) or ""
    gear_id = _safe_int(getattr(activity, "gear_id", None))

    if gear_id is not None:
        _resolve_gear_name(client, gear_id)

    return {
        "strava_id": int(activity.id),
        "name": name,
        "activity_type": activity_type,
        "category": category_for_type(activity_type),
        "start_date": start.replace(tzinfo=None),
        "distance_meters": _safe_float(getattr(activity, "distance", None)),
        "moving_time_seconds": _safe_int(getattr(activity, "moving_time", None)),
        "elapsed_time_seconds": _safe_int(getattr(activity, "elapsed_time", None)),
        "elevation_gain_meters": _safe_float(getattr(activity, "total_elevation_gain", None)),
        "avg_speed_mps": _safe_float(getattr(activity, "average_speed", None)),
        "avg_heartrate": _safe_float(getattr(activity, "average_heartrate", None)),
        "max_heartrate": _safe_float(getattr(activity, "max_heartrate", None)),
        "avg_cadence": _safe_float(getattr(activity, "average_cadence", None)),
        "description": description or None,
        "private_note": private_note or None,
        "gear_id": gear_id,
        "gear_name": GEAR_CACHE.get(gear_id) if gear_id else None,
        "suffer_score": _safe_float(getattr(activity, "suffer_score", None)),
        "is_workout": is_workout(start.weekday(), name, description, private_note),
        "hidden": False,
        "detail_synced": True,
        "location_city": getattr(activity, "location_city", None),
        "location_state": getattr(activity, "location_state", None),
        "source": "strava",
    }


def upsert_activity(conn: duckdb.DuckDBPyConnection, row: dict[str, Any]) -> None:
    synced_at = datetime.now()
    conn.execute(
        """
        INSERT INTO activities (
            strava_id, name, activity_type, category, start_date,
            distance_meters, moving_time_seconds, elapsed_time_seconds,
            elevation_gain_meters, avg_speed_mps, avg_heartrate, max_heartrate,
            avg_cadence, description, private_note, gear_id, gear_name, suffer_score,
            is_workout, hidden, detail_synced, location_city, location_state, source, synced_at
        ) VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
        ON CONFLICT (strava_id) DO UPDATE SET
            name = excluded.name,
            activity_type = excluded.activity_type,
            category = excluded.category,
            start_date = excluded.start_date,
            distance_meters = excluded.distance_meters,
            moving_time_seconds = excluded.moving_time_seconds,
            elapsed_time_seconds = excluded.elapsed_time_seconds,
            elevation_gain_meters = excluded.elevation_gain_meters,
            avg_speed_mps = excluded.avg_speed_mps,
            avg_heartrate = excluded.avg_heartrate,
            max_heartrate = excluded.max_heartrate,
            avg_cadence = excluded.avg_cadence,
            description = excluded.description,
            private_note = excluded.private_note,
            detail_synced = excluded.detail_synced,
            gear_id = excluded.gear_id,
            gear_name = excluded.gear_name,
            suffer_score = excluded.suffer_score,
            is_workout = excluded.is_workout,
            hidden = activities.hidden,
            location_city = excluded.location_city,
            location_state = excluded.location_state,
            synced_at = excluded.synced_at
        """,
        [
            row["strava_id"],
            row["name"],
            row["activity_type"],
            row["category"],
            row["start_date"],
            row["distance_meters"],
            row["moving_time_seconds"],
            row["elapsed_time_seconds"],
            row["elevation_gain_meters"],
            row["avg_speed_mps"],
            row["avg_heartrate"],
            row["max_heartrate"],
            row["avg_cadence"],
            row["description"],
            row["private_note"],
            row["gear_id"],
            row["gear_name"],
            row["suffer_score"],
            row["is_workout"],
            row["hidden"],
            row["detail_synced"],
            row["location_city"],
            row["location_state"],
            row["source"],
            synced_at,
        ],
    )


def _is_rate_limit_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "rate limit" in msg or "too many requests" in msg


def _fetch_activity_with_retry(client: Client, activity_id: int) -> Any:
    for attempt in range(MAX_RETRIES):
        try:
            time.sleep(_request_delay())
            return client.get_activity(activity_id)
        except Exception as exc:
            if _is_rate_limit_error(exc) and attempt < MAX_RETRIES - 1:
                wait = RATE_LIMIT_SLEEP_SECONDS * (attempt + 1)
                time.sleep(wait)
                continue
            raise
    raise RuntimeError(f"Failed to fetch activity {activity_id}")


def _activity_in_db(conn: duckdb.DuckDBPyConnection, activity_id: int) -> bool:
    """Skip re-fetch if full activity detail was already synced."""
    row = conn.execute(
        "SELECT detail_synced FROM activities WHERE strava_id = ?",
        [activity_id],
    ).fetchone()
    return row is not None and bool(row[0])


def _set_sync_metadata(conn: duckdb.DuckDBPyConnection, key: str, value: str) -> None:
    conn.execute(
        """
        INSERT INTO sync_metadata (key, value, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT (key) DO UPDATE SET
            value = excluded.value,
            updated_at = excluded.updated_at
        """,
        [key, value, datetime.now()],
    )


def _sync_window(
    client: Client,
    conn: duckdb.DuckDBPyConnection,
    window: dict[str, Any],
    *,
    refresh: bool = False,
    max_fetches: int | None = None,
    fetched_so_far: int = 0,
) -> tuple[dict[str, int], int]:
    """Sync activities within a single date window. Returns stats and total fetch count."""
    stats = {"listed": 0, "upserted": 0, "skipped": 0, "errors": 0}
    seen_gear: set[int] = set()
    fetches = fetched_so_far

    activity_list = client.get_activities(
        after=window["start"],
        before=window["end_exclusive"],
        limit=200,
    )
    for summary in activity_list:
        if max_fetches is not None and fetches >= max_fetches:
            break

        stats["listed"] += 1
        activity_id = int(summary.id)

        if not refresh and _activity_in_db(conn, activity_id):
            stats["skipped"] += 1
            continue

        try:
            activity = _fetch_activity_with_retry(client, activity_id)
            row = activity_to_row(client, activity)
            upsert_activity(conn, row)
            stats["upserted"] += 1
            fetches += 1

            gear_id = row.get("gear_id")
            if gear_id and gear_id not in seen_gear:
                _upsert_gear(conn, client, gear_id)
                seen_gear.add(gear_id)
        except Exception as exc:
            stats["errors"] += 1
            if _is_rate_limit_error(exc):
                break

    return stats, fetches


def sync_strava(*, refresh: bool = False, limit: int | None = None) -> dict[str, Any]:
    """
    Sync Strava activities for configured date windows into DuckDB.

    By default uses sync.windows in settings.yaml (June 2025 + June 2026).
    Skips activities already detail-synced unless refresh=True.
    Use limit=5 to backfill gradually when rate-limited.
    """
    windows = parse_sync_windows()
    client = get_strava_client()
    conn = get_connection()

    results: list[dict[str, Any]] = []
    totals = {"listed": 0, "upserted": 0, "skipped": 0, "errors": 0}
    fetches = 0

    try:
        for window in windows:
            if limit is not None and fetches >= limit:
                break
            window_stats, fetches = _sync_window(
                client, conn, window, refresh=refresh, max_fetches=limit, fetched_so_far=fetches
            )
            window_stats["label"] = window["label"]
            results.append(window_stats)
            for key in totals:
                totals[key] += window_stats[key]

        _set_sync_metadata(
            conn,
            "strava_last_sync_at",
            datetime.now(timezone.utc).isoformat(),
        )
        _set_sync_metadata(
            conn,
            "strava_last_sync_windows",
            ", ".join(w["label"] for w in windows),
        )
    finally:
        conn.close()

    return {"windows": results, **totals}


def format_pace(avg_speed_mps: float | None) -> str:
    if not avg_speed_mps or avg_speed_mps <= 0:
        return "—"
    sec_per_mile = METERS_PER_MILE / avg_speed_mps
    minutes = int(sec_per_mile // 60)
    seconds = int(sec_per_mile % 60)
    return f"{minutes}:{seconds:02d}/mi"


def format_distance_miles(distance_meters: float | None) -> str:
    if distance_meters is None:
        return "—"
    return f"{distance_meters / METERS_PER_MILE:.2f}"


def format_duration(seconds: int | None) -> str:
    if seconds is None:
        return "—"
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"
