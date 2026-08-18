#!/usr/bin/env python3
"""Smoke test : lit ~10 mails recents d'une boite connectee et les range dans la base locale.

Usage:
  uv run python scripts/smoke_read.py [email]

Sans argument, prend la premiere boite connectee trouvee. Affiche l'expediteur et
le sujet des messages importes (donnees locales, sur ta machine).
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
    email = sys.argv[1] if len(sys.argv) > 1 else "you@example.com"
    print(f"Chargement des credentials pour {email}...")
    creds = auth.load_credentials(email)
    service = build("gmail", "v1", credentials=creds, cache_discovery=False)
    client = GmailClient(service)

    layout = paths.ensure_runtime_dirs(paths.runtime_dir())
    db = Database(layout["db"])
    store = Store(db)
    acc = store.upsert_account(email)

    ids, _ = client.list_message_ids(max_results=10)
    for gid in ids:
        raw = client.get_message(gid)
        fields, _atts = parse_gmail_message(raw)
        store.upsert_message(acc, gid, **fields)

    print(f"{len(ids)} messages importes dans {layout['db']}\n")
    rows = db.read().execute(
        "SELECT addr_from, subject, is_unread FROM messages "
        "WHERE account_id=? ORDER BY internal_date DESC LIMIT 10", (acc,)
    ).fetchall()
    for r in rows:
        frm = (r["addr_from"] or "")[:38]
        subj = (r["subject"] or "(sans sujet)")[:55]
        flag = "*" if r["is_unread"] else " "
        print(f"  {flag} {frm:38} | {subj}")
    db.close()
    print("\nOK : lecture live -> SQLite validee.")


if __name__ == "__main__":
    main()
