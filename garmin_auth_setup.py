"""
One-time Garmin Connect login.

Handles MFA and saves a local session to data/garmin_tokens/ so sync scripts
can run without prompting again.

EAD March 2026
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.sync.garmin_client import GARMIN_TOKEN_DIR, login_garmin


def main() -> None:
    print("Logging in to Garmin Connect...")
    print(f"Tokens will be saved to: {GARMIN_TOKEN_DIR}")
    try:
        login_garmin(allow_mfa=True)
    except RuntimeError as e:
        print(f"\nLogin failed:\n{e}")
        sys.exit(1)

    print("\n--- GARMIN AUTH SUCCESSFUL ---")
    print("You can now sync without MFA:")
    print("  uv run python scripts/sync_garmin.py")
    print("  uv run python scripts/sync_all.py --garmin-only")


if __name__ == "__main__":
    main()
