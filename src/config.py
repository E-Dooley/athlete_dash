"""Load project configuration from config/settings.yaml."""

from __future__ import annotations

from datetime import date, datetime, time, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "config" / "settings.yaml"
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "athlete.duckdb"


@lru_cache
def load_settings() -> dict[str, Any]:
    with CONFIG_PATH.open() as f:
        return yaml.safe_load(f)


def parse_date(value: date | str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.strptime(str(value), "%Y-%m-%d").date()


def parse_sync_windows(settings: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Return sync windows as {start, end, end_exclusive, label} with UTC datetimes."""
    settings = settings or load_settings()
    sync_cfg = settings.get("sync", {})
    windows = sync_cfg.get("windows")
    if not windows:
        start = parse_date(sync_cfg["start_date"])
        return [
            {
                "start": datetime.combine(start, time.min, tzinfo=timezone.utc),
                "end": datetime.now(timezone.utc),
                "end_exclusive": datetime.now(timezone.utc),
                "label": f"from {start}",
            }
        ]

    parsed: list[dict[str, Any]] = []
    for window in windows:
        start_day = parse_date(window["start"])
        end_day = parse_date(window["end"])
        end_exclusive = datetime.combine(
            date.fromordinal(end_day.toordinal() + 1),
            time.min,
            tzinfo=timezone.utc,
        )
        parsed.append(
            {
                "start": datetime.combine(start_day, time.min, tzinfo=timezone.utc),
                "end": datetime.combine(end_day, time.max, tzinfo=timezone.utc),
                "end_exclusive": end_exclusive,
                "label": window.get("label", f"{start_day} – {end_day}"),
            }
        )
    return parsed


def iter_sync_days(settings: dict[str, Any] | None = None):
    """Yield each calendar day covered by configured sync windows."""
    from datetime import timedelta

    for window in parse_sync_windows(settings):
        start_day = window["start"].date()
        end_day = window["end"].date()
        day = start_day
        while day <= end_day:
            yield day
            day += timedelta(days=1)


def category_for_type(activity_type: str) -> str:
    """Map Strava activity or sport type to run / cross_train / strength / mobility / other."""
    settings = load_settings()
    categories = settings.get("activity_categories", {})
    for category, spec in categories.items():
        types = spec.get("types", spec) if isinstance(spec, dict) else spec
        if activity_type in types:
            return category
    return "other"


def category_label(category: str) -> str:
    """Display label for a category (e.g. mobility -> Mobility)."""
    settings = load_settings()
    spec = settings.get("activity_categories", {}).get(category)
    if isinstance(spec, dict) and "label" in spec:
        return spec["label"]
    return category.replace("_", " ").title()


def is_workout(
    start_weekday: int,
    name: str | None,
    description: str | None,
    private_note: str | None = None,
) -> bool:
    """Detect coach workout: Wednesday or speedsters in title/description/private note."""
    settings = load_settings()
    detection = settings.get("workout_detection", {})
    weekday_name = detection.get("weekday", "wednesday").lower()
    weekday_map = {
        "monday": 0,
        "tuesday": 1,
        "wednesday": 2,
        "thursday": 3,
        "friday": 4,
        "saturday": 5,
        "sunday": 6,
    }
    if start_weekday == weekday_map.get(weekday_name, 2):
        return True
    text = f"{name or ''} {description or ''} {private_note or ''}".lower()
    for keyword in detection.get("title_keywords", ["speedsters"]):
        if keyword.lower() in text:
            return True
    return False
