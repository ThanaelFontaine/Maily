#!/usr/bin/env python3
"""Connects a Gmail mailbox through OAuth (loopback) and keeps the token in the encrypted store.

Usage:
  uv run python scripts/connect_account.py

Opens the browser for the Google consent. On the "unverified app" screen:
Advanced, then Go to Maily (see docs/GOOGLE_CLOUD_SETUP.md). The refresh token
is then stored in secrets.enc (encrypted), indexed by the address of the
connected account. Command-line equivalent of the "+ Add account" button of
the app.
"""
from __future__ import annotations
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from core import auth, paths
from core.db import Database
from core.store import Store


def main():
    print("Opening the browser for the Google consent...")
    print("(On the 'unverified app' screen: Advanced, then Go to Maily)")
    email = auth.run_local_auth(open_browser=True)
    # Save the account in the local database (the rail lists the accounts of the database).
    layout = paths.ensure_runtime_dirs(paths.runtime_dir())
    db = Database(layout["db"])
    Store(db).upsert_account(email)
    db.close()
    print(f"OK: mailbox connected, token stored and account saved: {email}")


if __name__ == "__main__":
    main()
