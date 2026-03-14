"""
Script that pulls down strava data from the latest activity

EAD March 2026
"""
import os
import polars as pl
from dotenv import load_dotenv
from stravalib.client import Client

load_dotenv()

# 1. Setup the Client
client = Client()
client_id = os.getenv('STRAVA_CLIENT_ID')
client_secret = os.getenv('STRAVA_CLIENT_SECRET')
refresh_token = os.getenv('STRAVA_REFRESH_TOKEN')

# 2. Refresh the Access Token
# (Strava tokens expire every 6 hours, so we do this every time)
res = client.refresh_access_token(
    client_id=client_id,
    client_secret=client_secret,
    refresh_token=refresh_token
)
client.access_token = res['access_token']
print("Handshake refreshed!")

# 3. Get your latest activity
activities = client.get_activities(limit=1)
latest_activity = list(activities)[0]
print(f"Fetching: {latest_activity.name} ({latest_activity.start_date})")

# 4. Fetch the high-res data streams
types = ['time', 'distance', 'latlng', 'altitude', 'heartrate', 'cadence', 'velocity_smooth']
streams = client.get_activity_streams(latest_activity.id, types=types, resolution='high')

# 5. Convert to Polars
# We create a dictionary of the data arrays and load into a DataFrame
data_dict = {s_type: streams[s_type].data for s_type in streams.keys()}
df = pl.DataFrame(data_dict)

print("\n--- Biomechanics Data Preview ---")
print(df.head())

# Optional: Save to a parquet file for your dashboard to read
df.write_parquet("latest_activity.parquet")