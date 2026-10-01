#!/usr/bin/env python3
"""Smoke test: reads ~10 recent messages of a connected mailbox and stores them in the local database.

Usage:
  uv run python scripts/smoke_read.py [email]

Without an argument, takes the first Gmail account saved in the local database. Prints the sender and
the subject of the imported messages (local data, on your machine).
"""
from __future__ import annotations
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from googleapiclient.discovery import build
from core import auth, paths
from core.db import Database
from core.store import Store
from core.gmail import GmailClient, parse_gmail_message


def main():
    layout = paths.ensure_runtime_dirs(paths.runtime_dir())
    if len(sys.argv) > 1:
        email = sys.argv[1]
    else:
        db0 = Database(layout["db"])
        accs = [a for a in Store(db0).list_accounts() if (a["provider"] or "gmail") == "gmail"]
        db0.close()
        if not accs:
            sys.exit("No Gmail account in the database: connect one (scripts/connect_account.py) or pass the address as an argument.")
        email = accs[0]["email"]
    print(f"Loading the credentials of {email}...")
    creds = auth.load_credentials(email)
    service = build("gmail", "v1", credentials=creds, cache_discovery=False)
    client = GmailClient(service)

    db = Database(layout["db"])
    store = Store(db)
    acc = store.upsert_account(email)

    ids, _ = client.list_message_ids(max_results=10)
    for gid in ids:
        raw = client.get_message(gid)
        fields, _atts = parse_gmail_message(raw)
        store.upsert_message(acc, gid, **fields)

    print(f"{len(ids)} messages imported into {layout['db']}\n")
    rows = db.read().execute(
        "SELECT addr_from, subject, is_unread FROM messages "
        "WHERE account_id=? ORDER BY internal_date DESC LIMIT 10", (acc,)
    ).fetchall()
    for r in rows:
        frm = (r["addr_from"] or "")[:38]
        subj = (r["subject"] or "(no subject)")[:55]
        flag = "*" if r["is_unread"] else " "
        print(f"  {flag} {frm:38} | {subj}")
    db.close()
    print("\nOK: live read into SQLite works.")


if __name__ == "__main__":
    main()
