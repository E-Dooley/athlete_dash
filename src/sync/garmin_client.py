"""Garmin Connect authentication helpers."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from garminconnect import Garmin
from garminconnect.exceptions import (
    GarminConnectAuthenticationError,
    GarminConnectTooManyRequestsError,
)

from src.config import DATA_DIR

load_dotenv()

GARMIN_TOKEN_DIR = DATA_DIR / "garmin_tokens"


def _credentials() -> tuple[str, str]:
    email = os.getenv("GARMIN_EMAIL")
    password = os.getenv("GARMIN_PASSWORD")
    if not email or not password:
        raise RuntimeError(
            "Missing Garmin credentials. Set GARMIN_EMAIL and GARMIN_PASSWORD in .env"
        )
    return email, password


def _prompt_mfa() -> str:
    print("\nGarmin sent a verification code (authenticator app, SMS, or email).")
    return input("Enter MFA code: ").strip()


def login_garmin(*, allow_mfa: bool = False) -> Garmin:
    """
    Log in to Garmin Connect and cache tokens locally.

    Args:
        allow_mfa: If True, prompt for MFA code when required (use in auth setup only).
    """
    email, password = _credentials()
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    client = Garmin(
        email,
        password,
        prompt_mfa=_prompt_mfa if allow_mfa else None,
    )

    try:
        client.login(tokenstore=str(GARMIN_TOKEN_DIR))
    except GarminConnectTooManyRequestsError as e:
        raise RuntimeError(
            "Garmin is rate-limiting login attempts (429). "
            "Wait 15–30 minutes, then run:\n"
            "  uv run python garmin_auth_setup.py"
        ) from e
    except GarminConnectAuthenticationError as e:
        if "MFA" in str(e):
            raise RuntimeError(
                "Garmin MFA is required before sync can run unattended.\n"
                "Run once interactively:\n"
                "  uv run python garmin_auth_setup.py"
            ) from e
        raise RuntimeError(f"Garmin login failed: {e}") from e

    return client


def get_garmin_client() -> Garmin:
    """Return an authenticated client using cached tokens (no MFA prompt)."""
    if not GARMIN_TOKEN_DIR.exists() or not any(GARMIN_TOKEN_DIR.iterdir()):
        raise RuntimeError(
            "No cached Garmin session found.\n"
            "Run once to log in (MFA supported):\n"
            "  uv run python garmin_auth_setup.py"
        )
    return login_garmin(allow_mfa=False)


def tokens_cached() -> bool:
    return GARMIN_TOKEN_DIR.exists() and any(GARMIN_TOKEN_DIR.iterdir())
