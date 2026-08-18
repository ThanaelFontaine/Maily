from __future__ import annotations
from googleapiclient.discovery import build
from core.auth import load_credentials
from core.gmail import GmailClient
from core.sync import Syncer


def build_gmail_client(email) -> GmailClient:
    creds = load_credentials(email)
    service = build("gmail", "v1", credentials=creds, cache_discovery=False)
    return GmailClient(service)


def sync_account(store, email, account_id, full=False, query=None) -> int:
    client = build_gmail_client(email)
    syncer = Syncer(store, client, account_id)
    if full:
        return syncer.backfill(query=query)
    return syncer.incremental()
