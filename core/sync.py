from __future__ import annotations
from googleapiclient.errors import HttpError
from core.gmail import parse_gmail_message, HistoryExpired


def _status(e):
    return getattr(e, "status_code", None) or getattr(getattr(e, "resp", None), "status", None)


class Syncer:
    def __init__(self, store, client, account_id):
        self.store = store
        self.client = client
        self.account_id = account_id

    def _store_message(self, raw) -> int:
        fields, atts = parse_gmail_message(raw)
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
