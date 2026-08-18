from __future__ import annotations
from googleapiclient.discovery import build
from core.auth import load_credentials
from core.gmail import GmailClient
from core.sync import Syncer
from core import sender


def build_gmail_client(email) -> GmailClient:
    creds = load_credentials(email)
    service = build("gmail", "v1", credentials=creds, cache_discovery=False)
    return GmailClient(service)


def send_from_account(store, email, account_id, payload) -> dict:
    client = build_gmail_client(email)
    return sender.send_message(
        store, client, account_id, email,
        payload["to"], payload.get("subject", ""), payload.get("body_text", ""),
        body_html=payload.get("body_html"), cc=payload.get("cc"),
        in_reply_to=payload.get("in_reply_to"), thread_id=payload.get("thread_id"),
    )


def sync_account(store, email, account_id, full=False, query=None) -> int:
    client = build_gmail_client(email)
    syncer = Syncer(store, client, account_id)
    if full:
        return syncer.backfill(query=query)
    return syncer.incremental()
