"""
Evan's Athlete Dashboard

EAD March 2026
"""

from __future__ import annotations

import sys
from pathlib import Path

import polars as pl
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.config import DB_PATH, category_label, load_settings, parse_sync_windows
from src.db.connection import get_connection, init_db
from src.sync.garmin_sync import sync_garmin
from src.sync.merge import merge_strava_garmin
from src.sync.strava_sync import format_distance_miles, format_duration, format_pace, sync_strava

st.set_page_config(page_title="Evan's Athlete Dashboard", layout="wide")
st.title("Evan's Athlete Dashboard")

settings = load_settings()
sync_windows = parse_sync_windows()
sync_window_labels = ", ".join(w["label"] for w in sync_windows)


def load_activities(include_hidden: bool = False) -> pl.DataFrame:
    if not DB_PATH.exists():
        return pl.DataFrame()

    conn = get_connection()
    try:
        hidden_filter = "AND a.hidden = FALSE" if not include_hidden else ""
        query = f"""
            SELECT
                a.strava_id,
                a.start_date AS date,
                a.name,
                a.activity_type AS type,
                a.category,
                a.distance_meters,
                a.moving_time_seconds,
                a.avg_speed_mps,
                a.avg_heartrate,
                a.max_heartrate,
                a.avg_cadence,
                a.gear_name,
                a.is_workout,
                a.hidden,
                a.location_city,
                a.location_state,
                a.description,
                a.private_note,
                a.garmin_activity_id,
                a.source,
                w.sleep_hours,
                w.hrv,
                w.body_battery_avg,
                l.hydration_oz,
                l.stretch_logged,
                l.roll_logged
            FROM activities a
            LEFT JOIN daily_wellness w
                ON CAST(a.start_date AS DATE) = w.day
            LEFT JOIN daily_lifestyle l
                ON CAST(a.start_date AS DATE) = l.day
            WHERE 1=1 {hidden_filter}
            ORDER BY a.start_date DESC
        """
        return conn.execute(query).pl()
    finally:
        conn.close()


def display_dataframe(df: pl.DataFrame) -> pl.DataFrame:
    if df.is_empty():
        return df

    display = df.with_columns(
        pl.col("date").dt.strftime("%Y-%m-%d %H:%M").alias("date"),
        pl.col("distance_meters").map_elements(
            lambda m: format_distance_miles(m), return_dtype=pl.Utf8
        ).alias("distance_mi"),
        pl.col("moving_time_seconds").map_elements(
            lambda s: format_duration(s), return_dtype=pl.Utf8
        ).alias("duration"),
        pl.col("avg_speed_mps").map_elements(
            lambda s: format_pace(s), return_dtype=pl.Utf8
        ).alias("pace"),
        pl.col("avg_heartrate").round(0).alias("avg_hr"),
        pl.col("is_workout").alias("workout"),
        pl.col("category").map_elements(category_label, return_dtype=pl.Utf8).alias("category"),
        pl.col("location_city").fill_null("").alias("city"),
        pl.col("location_state").fill_null("").alias("state"),
        pl.when(pl.col("garmin_activity_id").is_not_null())
        .then(pl.lit("both"))
        .otherwise(pl.col("source"))
        .alias("source"),
        pl.col("sleep_hours").round(1).alias("sleep_hr"),
        pl.col("hydration_oz").round(0).alias("hydration_oz"),
        pl.col("stretch_logged").fill_null(False).alias("stretch"),
        pl.col("roll_logged").fill_null(False).alias("roll"),
    ).with_columns(
        (pl.col("city") + pl.when(pl.col("state") != "").then(pl.lit(", ") + pl.col("state")).otherwise(pl.lit("")))
        .alias("location")
    )

    columns = [
        "date",
        "name",
        "type",
        "category",
        "distance_mi",
        "duration",
        "pace",
        "avg_hr",
        "workout",
        "sleep_hr",
        "hydration_oz",
        "stretch",
        "roll",
        "gear_name",
        "location",
        "source",
    ]
    existing = [c for c in columns if c in display.columns]
    return display.select(existing)


# --- Sidebar ---
st.sidebar.header("Data")
st.sidebar.caption(f"Sync scope: **{sync_window_labels}**")

col_s, col_g = st.sidebar.columns(2)
with col_s:
    sync_strava_btn = st.button("Sync Strava", type="primary")
with col_g:
    sync_garmin_btn = st.button("Sync Garmin")

if sync_strava_btn:
    with st.sidebar.status("Syncing Strava...", expanded=True) as status:
        try:
            init_db()
            result = sync_strava()
            status.update(
                label=f"Strava: {result['upserted']} upserted, {result['errors']} errors",
                state="complete",
            )
        except Exception as e:
            status.update(label="Strava sync failed", state="error")
            st.sidebar.error(str(e))

if sync_garmin_btn:
    with st.sidebar.status("Syncing Garmin...", expanded=True) as status:
        try:
            init_db()
            gstats = sync_garmin()
            merge = merge_strava_garmin()
            status.update(
                label=(
                    f"Garmin: {gstats['wellness_rows']} wellness days, "
                    f"{merge['matched']} matched runs"
                ),
                state="complete",
            )
        except RuntimeError as e:
            status.update(label="Garmin auth needed", state="error")
            st.sidebar.error(str(e))
        except Exception as e:
            status.update(label="Garmin sync failed", state="error")
            st.sidebar.error(str(e))

if DB_PATH.exists():
    conn = get_connection()
    try:
        count = conn.execute("SELECT COUNT(*) FROM activities").fetchone()[0]
        st.sidebar.metric("Activities", count)
        wellness = conn.execute("SELECT COUNT(*) FROM daily_wellness").fetchone()[0]
        st.sidebar.metric("Wellness days", wellness)
        garmin_meta = conn.execute(
            "SELECT value FROM sync_metadata WHERE key = 'garmin_last_sync_at'"
        ).fetchone()
        if garmin_meta:
            st.sidebar.caption(f"Garmin last sync: {garmin_meta[0][:19]}")
    finally:
        conn.close()
else:
    st.sidebar.info("No local database yet. Use **Sync Strava** or **Sync Garmin**.")

show_hidden = st.sidebar.checkbox("Show hidden activities", value=False)

# --- Main ---
st.subheader("Activity Log")

raw = load_activities(include_hidden=show_hidden)

if raw.is_empty():
    st.info(
        f"No activities loaded yet. Sync **Strava** and/or **Garmin** for **{sync_window_labels}**."
    )
else:
    col1, col2, col3 = st.columns(3)
    categories = sorted(raw["category"].unique().to_list())
    types = sorted(raw["type"].unique().to_list())

    with col1:
        cat_filter = st.multiselect("Category", categories, default=categories)
    with col2:
        type_filter = st.multiselect("Type", types, default=types)
    with col3:
        runs_only = st.checkbox("Runs only", value=False)

    filtered = raw.filter(
        pl.col("category").is_in(cat_filter) & pl.col("type").is_in(type_filter)
    )
    if runs_only:
        filtered = filtered.filter(pl.col("category") == "run")

    st.caption(f"Showing {filtered.height} of {raw.height} activities")

    table = display_dataframe(filtered)
    st.dataframe(table, width="stretch", hide_index=True)

    with st.expander("Private notes (full text)"):
        notes_df = filtered.filter(
            pl.col("private_note").is_not_null() & (pl.col("private_note").str.len_chars() > 0)
        ).select(
            pl.col("date").dt.strftime("%Y-%m-%d").alias("date"),
            "name",
            "private_note",
        )
        if notes_df.is_empty():
            st.write("No private notes on record for filtered activities.")
        else:
            for row in notes_df.iter_rows(named=True):
                st.markdown(f"**{row['date']} — {row['name']}**")
                st.write(row["private_note"])
                st.divider()

    with st.expander("Public descriptions (full text)"):
        desc_df = filtered.filter(
            pl.col("description").is_not_null() & (pl.col("description").str.len_chars() > 0)
        ).select(
            pl.col("date").dt.strftime("%Y-%m-%d").alias("date"),
            "name",
            "description",
        )
        if desc_df.is_empty():
            st.write("No public descriptions for filtered activities.")
        else:
            for row in desc_df.iter_rows(named=True):
                st.markdown(f"**{row['date']} — {row['name']}**")
                st.write(row["description"])
                st.divider()
