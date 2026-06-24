"""Authenticated Strava API client."""

from __future__ import annotations

import os

from dotenv import load_dotenv
from stravalib.client import Client

load_dotenv()


def get_strava_client() -> Client:
    client = Client()
    client_id = os.getenv("STRAVA_CLIENT_ID")
    client_secret = os.getenv("STRAVA_CLIENT_SECRET")
    refresh_token = os.getenv("STRAVA_REFRESH_TOKEN")

    if not all([client_id, client_secret, refresh_token]):
        raise RuntimeError(
            "Missing Strava credentials. Set STRAVA_CLIENT_ID, "
            "STRAVA_CLIENT_SECRET, and STRAVA_REFRESH_TOKEN in .env"
        )

    res = client.refresh_access_token(
        client_id=client_id,
        client_secret=client_secret,
        refresh_token=refresh_token,
    )
    client.access_token = res["access_token"]
    return client
