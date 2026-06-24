"""Sync Garmin Connect wellness, lifestyle, and activities into DuckDB."""

from __future__ import annotations

import json
import time
from datetime import date, datetime
from typing import Any

import duckdb
from garminconnect import Garmin

from src.config import iter_sync_days, load_settings
from src.db.connection import get_connection
from src.sync.garmin_client import get_garmin_client

ML_PER_OZ = 29.5735
REQUEST_DELAY = 0.5


def _sleep_seconds(payload: dict[str, Any] | None) -> float | None:
    if not payload:
        return None
    dto = payload.get("dailySleepDTO") or payload.get("sleep") or payload
    if isinstance(dto, dict):
        for key in ("sleepTimeSeconds", "totalSleepSeconds", "durationInSeconds"):
            val = dto.get(key)
            if val:
                return float(val)
    return None


def _parse_wellness(
    client: Garmin, day: date
) -> dict[str, Any]:
    day_str = day.isoformat()
    sleep_hours = None
    sleep_score = None
    hrv = None
    body_battery = None
    resting_hr = None

    try:
        sleep_data = client.get_sleep_data(day_str)
        secs = _sleep_seconds(sleep_data)
        if secs:
            sleep_hours = round(secs / 3600, 2)
        dto = (sleep_data or {}).get("dailySleepDTO") or {}
        if dto.get("sleepScores") and isinstance(dto["sleepScores"], dict):
            sleep_score = dto["sleepScores"].get("overallScore")
        elif dto.get("sleepScore"):
            sleep_score = dto.get("sleepScore")
    except Exception:
        pass

    try:
        hrv_data = client.get_hrv_data(day_str)
        if hrv_data:
            summary = hrv_data.get("hrvSummary") or hrv_data
            hrv = summary.get("lastNightAvg") or summary.get("weeklyAvg")
    except Exception:
        pass

    try:
        bb = client.get_body_battery(day_str, day_str)
        if isinstance(bb, list) and bb:
            values = [p.get("bodyBatteryValue") for p in bb if p.get("bodyBatteryValue") is not None]
            if values:
                body_battery = sum(values) / len(values)
    except Exception:
        pass

    try:
        rhr = client.get_rhr_day(day_str)
        if rhr and isinstance(rhr, dict):
            entries = rhr.get("allMetrics") or rhr.get("metrics") or []
            for entry in entries:
                if entry.get("metricId") == 60 or entry.get("name") == "RestingHeartRate":
                    resting_hr = entry.get("value")
                    break
    except Exception:
        pass

    return {
        "day": day,
        "sleep_hours": sleep_hours,
        "sleep_score": sleep_score,
        "hrv": hrv,
        "body_battery_avg": body_battery,
        "resting_hr": resting_hr,
    }


def _lifestyle_flags(payload: dict[str, Any] | None) -> tuple[bool, bool]:
    """Detect stretch and roll habits from lifestyle logging response."""
    if not payload:
        return False, False

    keywords = load_settings().get("garmin", {}).get("lifestyle_keywords", {})
    stretch_kw = [k.lower() for k in keywords.get("stretch", ["stretch", "yoga"])]
    roll_kw = [k.lower() for k in keywords.get("roll", ["roll", "foam"])]

    stretch = False
    roll = False
    blob = json.dumps(payload).lower()

    for kw in stretch_kw:
        if kw in blob:
            stretch = True
            break
    for kw in roll_kw:
        if kw in blob:
            roll = True
            break

    return stretch, roll


def _parse_lifestyle(client: Garmin, day: date) -> dict[str, Any]:
    day_str = day.isoformat()
    hydration_ml = None
    stretch = False
    roll = False

    try:
        hydration = client.get_hydration_data(day_str)
        if hydration:
            hydration_ml = hydration.get("valueInML") or hydration.get("hydrationAmount")
            if hydration_ml is not None:
                hydration_ml = float(hydration_ml)
    except Exception:
        pass

    try:
        lifestyle = client.get_lifestyle_logging_data(day_str)
        s, r = _lifestyle_flags(lifestyle)
        stretch = stretch or s
        roll = roll or r
    except Exception:
        pass

    hydration_oz = hydration_ml / ML_PER_OZ if hydration_ml else None
    return {
        "day": day,
        "hydration_ml": hydration_ml,
        "hydration_oz": round(hydration_oz, 1) if hydration_oz else None,
        "stretch_logged": stretch,
        "roll_logged": roll,
    }


def _parse_garmin_activity(raw: dict[str, Any]) -> dict[str, Any] | None:
    activity_id = raw.get("activityId") or raw.get("activityUUID")
    if activity_id is None:
        return None

    start_raw = raw.get("startTimeLocal") or raw.get("startTimeGMT") or raw.get("beginTimestamp")
    if not start_raw:
        return None

    if isinstance(start_raw, (int, float)):
        start_date = datetime.fromtimestamp(start_raw / 1000 if start_raw > 1e12 else start_raw)
    else:
        start_date = datetime.fromisoformat(str(start_raw).replace("Z", "+00:00")).replace(tzinfo=None)

    type_dto = raw.get("activityType") or {}
    activity_type = type_dto.get("typeKey") if isinstance(type_dto, dict) else str(type_dto)

    distance = raw.get("distance")
    if distance is not None:
        distance = float(distance)

    duration = raw.get("duration") or raw.get("movingDuration") or raw.get("elapsedDuration")
    if duration is not None:
        duration = int(duration)

    return {
        "garmin_id": int(activity_id),
        "name": raw.get("activityName") or raw.get("name"),
        "activity_type": activity_type,
        "start_date": start_date,
        "distance_meters": distance,
        "duration_seconds": duration,
        "avg_heartrate": raw.get("averageHR") or raw.get("avgHR"),
    }


def _upsert_wellness(conn: duckdb.DuckDBPyConnection, row: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO daily_wellness (
            day, sleep_hours, sleep_score, hrv, body_battery_avg, resting_hr, synced_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (day) DO UPDATE SET
            sleep_hours = excluded.sleep_hours,
            sleep_score = excluded.sleep_score,
            hrv = excluded.hrv,
            body_battery_avg = excluded.body_battery_avg,
            resting_hr = excluded.resting_hr,
            synced_at = excluded.synced_at
        """,
        [
            row["day"],
            row["sleep_hours"],
            row["sleep_score"],
            row["hrv"],
            row["body_battery_avg"],
            row["resting_hr"],
            datetime.now(),
        ],
    )


def _upsert_lifestyle(conn: duckdb.DuckDBPyConnection, row: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO daily_lifestyle (
            day, hydration_ml, hydration_oz, stretch_logged, roll_logged, synced_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT (day) DO UPDATE SET
            hydration_ml = excluded.hydration_ml,
            hydration_oz = excluded.hydration_oz,
            stretch_logged = excluded.stretch_logged,
            roll_logged = excluded.roll_logged,
            synced_at = excluded.synced_at
        """,
        [
            row["day"],
            row["hydration_ml"],
            row["hydration_oz"],
            row["stretch_logged"],
            row["roll_logged"],
            datetime.now(),
        ],
    )


def _upsert_garmin_activity(conn: duckdb.DuckDBPyConnection, row: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO garmin_activities (
            garmin_id, name, activity_type, start_date, distance_meters,
            duration_seconds, avg_heartrate, synced_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (garmin_id) DO UPDATE SET
            name = excluded.name,
            activity_type = excluded.activity_type,
            start_date = excluded.start_date,
            distance_meters = excluded.distance_meters,
            duration_seconds = excluded.duration_seconds,
            avg_heartrate = excluded.avg_heartrate,
            synced_at = excluded.synced_at
        """,
        [
            row["garmin_id"],
            row["name"],
            row["activity_type"],
            row["start_date"],
            row["distance_meters"],
            row["duration_seconds"],
            row["avg_heartrate"],
            datetime.now(),
        ],
    )


def _sync_garmin_activities_for_day(
    client: Garmin, conn: duckdb.DuckDBPyConnection, day: date
) -> int:
    count = 0
    try:
        payload = client.get_activities_fordate(day.isoformat())
    except Exception:
        return 0

    activities: list[dict[str, Any]] = []
    if isinstance(payload, list):
        activities = payload
    elif isinstance(payload, dict):
        for key in ("activities", "activityList", "calendarItems"):
            if isinstance(payload.get(key), list):
                activities = payload[key]
                break

    for raw in activities:
        if not isinstance(raw, dict):
            continue
        row = _parse_garmin_activity(raw)
        if row:
            _upsert_garmin_activity(conn, row)
            count += 1
    return count


def sync_garmin() -> dict[str, int]:
    """Sync Garmin daily wellness, lifestyle, and activities for configured date windows."""
    client = get_garmin_client()
    conn = get_connection()

    stats = {
        "days": 0,
        "wellness_rows": 0,
        "lifestyle_rows": 0,
        "garmin_activities": 0,
        "errors": 0,
    }

    try:
        for day in iter_sync_days():
            stats["days"] += 1
            try:
                wellness = _parse_wellness(client, day)
                if any(wellness[k] is not None for k in ("sleep_hours", "sleep_score", "hrv", "body_battery_avg", "resting_hr")):
                    _upsert_wellness(conn, wellness)
                    stats["wellness_rows"] += 1

                lifestyle = _parse_lifestyle(client, day)
                if any(
                    lifestyle[k]
                    for k in ("hydration_ml", "hydration_oz", "stretch_logged", "roll_logged")
                ):
                    _upsert_lifestyle(conn, lifestyle)
                    stats["lifestyle_rows"] += 1

                stats["garmin_activities"] += _sync_garmin_activities_for_day(client, conn, day)
                time.sleep(REQUEST_DELAY)
            except Exception:
                stats["errors"] += 1

        conn.execute(
            """
            INSERT INTO sync_metadata (key, value, updated_at)
            VALUES ('garmin_last_sync_at', ?, ?)
            ON CONFLICT (key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
            """,
            [datetime.now().isoformat(), datetime.now()],
        )
    finally:
        conn.close()

    return stats
