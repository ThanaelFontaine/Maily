from __future__ import annotations
import base64
import os
import re
from googleapiclient.discovery import build
from core.auth import load_credentials
from core.gmail import GmailClient
from core.sync import Syncer
from core import sender


def _safe_name(name: str) -> str:
    name = re.sub(r"[^A-Za-z0-9._-]", "_", name or "file")
    return name[:120] or "file"


def fetch_attachment(store, email, message_id, att_id, attachments_dir):
    att = store.get_attachment(att_id)
    if not att or att["owner_id"] != message_id or att["owner_kind"] != "message":
        raise ValueError("piece jointe introuvable")
    lp = att["local_path"]
    if lp and os.path.exists(lp):
        with open(lp, "rb") as f:
            return f.read(), att["mime_type"], att["filename"]
    m = store.get_message(message_id)
    client = build_gmail_client(email)
    resp = client.get_attachment(m["gmail_id"], att["gmail_attachment_id"])
    data = base64.urlsafe_b64decode(resp["data"])
    os.makedirs(attachments_dir, exist_ok=True)
    path = os.path.join(attachments_dir, f"{att_id}_{_safe_name(att['filename'])}")
    with open(path, "wb") as f:
        f.write(data)
    store.set_attachment_path(att_id, path)
    return data, att["mime_type"], att["filename"]


def build_gmail_client(email) -> GmailClient:
    creds = load_credentials(email)
    service = build("gmail", "v1", credentials=creds, cache_discovery=False)
    return GmailClient(service)


def modify_message(store, email, message_id, add=None, remove=None) -> dict:
    m = store.get_message(message_id)
    if not m:
        raise ValueError("message introuvable")
    build_gmail_client(email).modify(m["gmail_id"], add=add, remove=remove)
    store.apply_local_labels(message_id, add=add, remove=remove)
    return {"ok": True}


def trash_message(store, email, message_id) -> dict:
    m = store.get_message(message_id)
    if not m:
        raise ValueError("message introuvable")
    build_gmail_client(email).trash(m["gmail_id"])
    store.set_trashed(message_id, True)
    return {"ok": True}


def untrash_message(store, email, message_id) -> dict:
    m = store.get_message(message_id)
    if not m:
        raise ValueError("message introuvable")
    build_gmail_client(email).untrash(m["gmail_id"])
    store.set_trashed(message_id, False)
    return {"ok": True}


_MAX_SEND_BYTES = 25 * 1024 * 1024


def send_from_account(store, email, account_id, payload) -> dict:
    attachments = []
    total = 0
    for a in payload.get("attachments") or []:
        data = base64.b64decode(a["data"])
        total += len(data)
        attachments.append({"filename": a.get("filename"), "mime_type": a.get("mime_type"), "data": data})
    if total > _MAX_SEND_BYTES:
        raise ValueError("Pieces jointes trop volumineuses (max 25 Mo au total pour l'envoi simple).")
    client = build_gmail_client(email)
    return sender.send_message(
        store, client, account_id, email,
        payload["to"], payload.get("subject", ""), payload.get("body_text", ""),
        body_html=payload.get("body_html"), cc=payload.get("cc"),
        in_reply_to=payload.get("in_reply_to"), thread_id=payload.get("thread_id"),
        attachments=attachments,
    )


def sync_account(store, email, account_id, full=False, query=None) -> int:
    client = build_gmail_client(email)
    syncer = Syncer(store, client, account_id)
    if full:
        return syncer.backfill(query=query)
    return syncer.incremental()
