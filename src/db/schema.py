"""DuckDB table definitions."""

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS sync_metadata (
    key VARCHAR PRIMARY KEY,
    value VARCHAR,
    updated_at TIMESTAMP DEFAULT current_timestamp
);

CREATE TABLE IF NOT EXISTS gear (
    gear_id BIGINT PRIMARY KEY,
    name VARCHAR,
    brand_name VARCHAR,
    distance_meters DOUBLE,
    synced_at TIMESTAMP DEFAULT current_timestamp
);

CREATE TABLE IF NOT EXISTS activities (
    strava_id BIGINT PRIMARY KEY,
    name VARCHAR,
    activity_type VARCHAR,
    category VARCHAR,
    start_date TIMESTAMP,
    distance_meters DOUBLE,
    moving_time_seconds INTEGER,
    elapsed_time_seconds INTEGER,
    elevation_gain_meters DOUBLE,
    avg_speed_mps DOUBLE,
    avg_heartrate DOUBLE,
    max_heartrate DOUBLE,
    avg_cadence DOUBLE,
    description VARCHAR,
    private_note VARCHAR,
    detail_synced BOOLEAN DEFAULT FALSE,
    gear_id BIGINT,
    gear_name VARCHAR,
    suffer_score DOUBLE,
    is_workout BOOLEAN DEFAULT FALSE,
    hidden BOOLEAN DEFAULT FALSE,
    location_city VARCHAR,
    location_state VARCHAR,
    garmin_activity_id BIGINT,
    source VARCHAR DEFAULT 'strava',
    synced_at TIMESTAMP DEFAULT current_timestamp
);

CREATE TABLE IF NOT EXISTS garmin_activities (
    garmin_id BIGINT PRIMARY KEY,
    name VARCHAR,
    activity_type VARCHAR,
    start_date TIMESTAMP,
    distance_meters DOUBLE,
    duration_seconds INTEGER,
    avg_heartrate DOUBLE,
    matched_strava_id BIGINT,
    synced_at TIMESTAMP DEFAULT current_timestamp
);

CREATE TABLE IF NOT EXISTS daily_wellness (
    day DATE PRIMARY KEY,
    sleep_hours DOUBLE,
    sleep_score DOUBLE,
    hrv DOUBLE,
    body_battery_avg DOUBLE,
    resting_hr DOUBLE,
    synced_at TIMESTAMP DEFAULT current_timestamp
);

CREATE TABLE IF NOT EXISTS daily_lifestyle (
    day DATE PRIMARY KEY,
    hydration_ml DOUBLE,
    hydration_oz DOUBLE,
    stretch_logged BOOLEAN DEFAULT FALSE,
    roll_logged BOOLEAN DEFAULT FALSE,
    synced_at TIMESTAMP DEFAULT current_timestamp
);

CREATE INDEX IF NOT EXISTS idx_activities_start_date ON activities(start_date);
CREATE INDEX IF NOT EXISTS idx_activities_category ON activities(category);
CREATE INDEX IF NOT EXISTS idx_garmin_activities_start_date ON garmin_activities(start_date);
"""
