"""DuckDB connection helpers."""

from __future__ import annotations

import duckdb

from src.config import DATA_DIR, DB_PATH, load_settings
from src.db.schema import SCHEMA_SQL


def _recompute_categories(conn: duckdb.DuckDBPyConnection) -> None:
    """Apply activity_categories from config to existing rows (no API call)."""
    categories = load_settings().get("activity_categories", {})
    for category, spec in categories.items():
        types = spec.get("types", spec) if isinstance(spec, dict) else spec
        if not types:
            continue
        placeholders = ", ".join("?" for _ in types)
        conn.execute(
            f"UPDATE activities SET category = ? WHERE activity_type IN ({placeholders})",
            [category, *types],
        )


def get_connection() -> duckdb.DuckDBPyConnection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect(str(DB_PATH))
    conn.execute(SCHEMA_SQL)
    conn.execute("ALTER TABLE activities ADD COLUMN IF NOT EXISTS private_note VARCHAR")
    conn.execute("ALTER TABLE activities ADD COLUMN IF NOT EXISTS detail_synced BOOLEAN DEFAULT FALSE")
    conn.execute("ALTER TABLE activities ADD COLUMN IF NOT EXISTS garmin_activity_id BIGINT")
    _recompute_categories(conn)
    return conn


def init_db() -> None:
    conn = get_connection()
    conn.close()
