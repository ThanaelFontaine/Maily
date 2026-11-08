from __future__ import annotations
from googleapiclient.errors import HttpError
import json
import logging
from core.gmail import parse_gmail_message, HistoryExpired, _headers_map
from core.rfc822_parse import UNREADABLE_LABEL, UNREADABLE_BODY

log = logging.getLogger("maily.sync")


def _status(e):
    return getattr(e, "status_code", None) or getattr(getattr(e, "resp", None), "status", None)


def _fallback_fields(raw: dict) -> dict:
    """Placeholder card for a Gmail message `parse_gmail_message` cannot read: the headers
    given by the API, a fixed body, the labels plus the local MAILY_UNREADABLE one."""
    def clean(v):
        return None if v is None else str(v).encode("utf-8", errors="replace").decode("utf-8")
    try:
        headers = _headers_map(raw.get("payload") or {})
    except Exception:
        headers = {}
    try:
        labels = [str(x) for x in (raw.get("labelIds") or [])]
    except Exception:
        labels = []
    try:
        date = int(raw["internalDate"]) if raw.get("internalDate") else None
    except (TypeError, ValueError):
        date = None
    return {
        "thread_id": raw.get("threadId"),
        "rfc822_message_id": clean(headers.get("message-id")),
        "direction": "out" if "SENT" in labels else "in",
        "addr_from": clean(headers.get("from")),
        "addr_to": clean(headers.get("to")),
        "addr_cc": clean(headers.get("cc")),
        "addr_bcc": clean(headers.get("bcc")),
        "subject": clean(headers.get("subject")),
        "snippet": UNREADABLE_BODY,
        "body_text": UNREADABLE_BODY,
        "body_html": None,
        "internal_date": date,
        "label_ids": json.dumps(labels + [UNREADABLE_LABEL]),
        "is_unread": 1 if "UNREAD" in labels else 0,
        "is_starred": 1 if "STARRED" in labels else 0,
        "is_trashed": 1 if "TRASH" in labels else 0,
        "has_attachments": 0,
    }


class Syncer:
    def __init__(self, store, client, account_id):
        self.store = store
        self.client = client
        self.account_id = account_id

    def _store_message(self, raw) -> int:
        # Only the analysis is guarded (never the network calls): a message that cannot be
        # parsed becomes a placeholder card instead of blocking the sync.
        try:
            fields, atts = parse_gmail_message(raw)
        except Exception as e:
            log.warning("unreadable Gmail message stored as a placeholder (%s)", type(e).__name__)
            fields, atts = _fallback_fields(raw), []
        mid = self.store.upsert_message(self.account_id, raw["id"], **fields)
        self.store.replace_attachments(mid, atts)
        return mid

    def _import(self, gid) -> bool:
        """Fetches a message again and upserts it. Returns False if the message is gone (404)."""
        try:
            raw = self.client.get_message(gid)
        except HttpError as e:
            if _status(e) in (404, 410):
                return False
            raise
        self._store_message(raw)
        return True

    def _profile_history_id(self):
        get_profile = getattr(self.client, "get_profile", None)
        if not get_profile:
            return None
        try:
            return (get_profile() or {}).get("historyId")
        except Exception:
            return None

    def backfill(self, query=None, page_size=100) -> int:
        acc = self.account_id
        page_token = self.store.get_sync_state(acc, "backfill_page_token") or None
        count = 0
        # Reliable checkpoint = current historyId of the mailbox (works even with 0 messages).
        checkpoint = self.store.get_sync_state(acc, "last_history_id") or self._profile_history_id() or None
        while True:
            ids, next_token = self.client.list_message_ids(
                query=query, page_token=page_token, max_results=page_size)
            for gid in ids:
                raw = self.client.get_message(gid)
                if checkpoint is None and raw.get("historyId"):
                    checkpoint = raw["historyId"]
                self._store_message(raw)
                count += 1
            page_token = next_token
            self.store.set_sync_state(acc, "backfill_page_token", page_token or "")
            if not next_token:
                break
        if checkpoint:
            self.store.set_sync_state(acc, "last_history_id", checkpoint)
        self.store.set_sync_state(acc, "backfill_done", "1")
        return count

    def incremental(self) -> int:
        acc = self.account_id
        start = self.store.get_sync_state(acc, "last_history_id")
        if not start:
            return self.backfill()
        page_token = None
        changed = 0
        latest = start
        # A message touched by several records (added, then labels) is fetched only once: each
        # fetch costs Gmail quota.
        fetched = set()
        try:
            while True:
                records, next_token, hist_id = self.client.list_history(start, page_token)
                for rec in records:
                    # messagesAdded + labelsAdded + labelsRemoved: fetch the whole message again
                    refetch = set()
                    for a in rec.get("messagesAdded", []):
                        refetch.add(a["message"]["id"])
                    for x in rec.get("labelsAdded", []):
                        refetch.add(x["message"]["id"])
                    for x in rec.get("labelsRemoved", []):
                        refetch.add(x["message"]["id"])
                    for gid in refetch - fetched:
                        fetched.add(gid)
                        if self._import(gid):
                            changed += 1
                    # messagesDeleted = permanent deletion: mark as trashed IF the message exists
                    for d in rec.get("messagesDeleted", []):
                        if self.store.mark_trashed_by_gmail_id(acc, d["message"]["id"]):
                            changed += 1
                # Resume point after each page: the last record handled. Without it, a failure
                # (Gmail quota) restarted everything from the same point at each sync, which hit
                # the quota again: the mailbox stayed frozen.
                ids = [int(r["id"]) for r in records if str(r.get("id", "")).isdigit()]
                if ids and next_token:
                    self.store.set_sync_state(acc, "last_history_id", str(max(ids)))
                if hist_id:
                    latest = hist_id
                if not next_token:
                    break
                page_token = next_token
        except HistoryExpired:
            self.store.set_sync_state(acc, "backfill_page_token", "")
            self.store.set_sync_state(acc, "last_history_id", "")
            return self.backfill()
        self.store.set_sync_state(acc, "last_history_id", latest)
        return changed
