#!/usr/bin/env python3
"""Saves in the local database the accounts already connected (token present in the encrypted store).

Usage:
  uv run python scripts/register_accounts.py email1 [email2 ...]

For each address: checks that a token exists in secrets.enc, then creates or
updates the account row in the database (the app's rail lists the accounts of
the database). Opens no browser. Idempotent.
"""
from __future__ import annotations
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from core import paths, secrets_store
from core.db import Database
from core.store import Store


def main():
    emails = sys.argv[1:]
    if not emails:
        sys.exit("Usage: register_accounts.py email1 [email2 ...]")
    layout = paths.ensure_runtime_dirs(paths.runtime_dir())
    db = Database(layout["db"])
    store = Store(db)
    for e in emails:
        if secrets_store.load_account_token(e):
            store.upsert_account(e)
            print(f"  saved: {e}")
        else:
            print(f"  SKIPPED (no token saved, connect it first): {e}")
    db.close()
    print("Done.")


if __name__ == "__main__":
    main()
