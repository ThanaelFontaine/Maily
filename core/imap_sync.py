"""Synchronisation IMAP (INBOX) vers le store local, en réutilisant le schéma
Gmail existant via des libellés synthétiques.

Mapping :
- gmail_id   = "{uidvalidity}.{uid}" (unique même si l'UIDVALIDITY change).
- label_ids  = ["INBOX"] (+ "UNREAD" si le flag \\Seen est absent).
- thread_id  = Message-ID (pas de fil IMAP).

Le client est injecté (testable sans réseau).
"""
from __future__ import annotations
import datetime
import json
from core.rfc822_parse import parse_rfc822


class ImapSyncer:
    def __init__(self, store, client, account_id, backfill_months: int = 12):
        self.store = store
        self.client = client
        self.account_id = account_id
        self.backfill_months = backfill_months

    def _since(self) -> datetime.date:
        return datetime.date.today() - datetime.timedelta(days=self.backfill_months * 31)

    def _store_one(self, uid, uidvalidity, raw, seen):
        fields, atts = parse_rfc822(raw)
        fields["label_ids"] = json.dumps(["INBOX"] if seen else ["INBOX", "UNREAD"])
        fields["is_unread"] = 0 if seen else 1
        mid = self.store.upsert_message(self.account_id, f"{uidvalidity}.{uid}", **fields)
        self.store.replace_attachments(mid, atts)

    def _run(self, uids, uidvalidity) -> int:
        count = 0
        for uid in uids:
            raw, seen = self.client.fetch(uid)
            self._store_one(uid, uidvalidity, raw, seen)
            count += 1
        return count

    def _save_anchor(self, uidvalidity, uids):
        self.store.set_sync_state(self.account_id, "imap_uidvalidity", uidvalidity)
        if uids:
            self.store.set_sync_state(self.account_id, "imap_last_uid", max(uids))
        elif self.store.get_sync_state(self.account_id, "imap_last_uid") is None:
            self.store.set_sync_state(self.account_id, "imap_last_uid", 0)

    def _full(self, uidvalidity) -> int:
        uids = self.client.search_uids(since=self._since())
        count = self._run(uids, uidvalidity)
        self._save_anchor(uidvalidity, uids)
        self.store.set_sync_state(self.account_id, "backfill_done", "1")
        return count

    def backfill(self) -> int:
        self.client.connect()
        try:
            return self._full(self.client.select_inbox())
        finally:
            self.client.logout()

    def incremental(self) -> int:
        self.client.connect()
        try:
            uidvalidity = self.client.select_inbox()
            stored = self.store.get_sync_state(self.account_id, "imap_uidvalidity")
            if stored is None or str(stored) != str(uidvalidity):
                # 1re synchro OU l'UIDVALIDITY a changé -> réimport complet (fenêtre).
                return self._full(uidvalidity)
            last_uid = int(self.store.get_sync_state(self.account_id, "imap_last_uid") or 0)
            uids = [u for u in self.client.search_uids(min_uid=last_uid + 1) if u > last_uid]
            count = self._run(uids, uidvalidity)
            if uids:
                self.store.set_sync_state(self.account_id, "imap_last_uid", max(uids))
            return count
        finally:
            self.client.logout()
