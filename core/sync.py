from __future__ import annotations
from core.gmail import parse_gmail_message, HistoryExpired


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

    def _import(self, gid) -> None:
        raw = self.client.get_message(gid)
        self._store_message(raw)

    def backfill(self, query=None, page_size=100) -> int:
        acc = self.account_id
        page_token = self.store.get_sync_state(acc, "backfill_page_token") or None
        count = 0
        first_history_id = self.store.get_sync_state(acc, "last_history_id") or None
        while True:
            ids, next_token = self.client.list_message_ids(
                query=query, page_token=page_token, max_results=page_size)
            for gid in ids:
                raw = self.client.get_message(gid)
                if first_history_id is None and raw.get("historyId"):
                    first_history_id = raw["historyId"]
                self._store_message(raw)
                count += 1
            page_token = next_token
            self.store.set_sync_state(acc, "backfill_page_token", page_token or "")
            if not next_token:
                break
        if first_history_id:
            self.store.set_sync_state(acc, "last_history_id", first_history_id)
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
        try:
            while True:
                records, next_token, hist_id = self.client.list_history(start, page_token)
                for rec in records:
                    for added in rec.get("messagesAdded", []):
                        self._import(added["message"]["id"])
                        changed += 1
                    for deleted in rec.get("messagesDeleted", []):
                        gid = deleted["message"]["id"]
                        self.store.upsert_message(acc, gid, is_trashed=1)
                        changed += 1
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
