"""Synchronisation IMAP vers le store local, en réutilisant le schéma Gmail.

Orange = **tout** : tous les dossiers IMAP, sans limite de date. Chaque dossier
devient un libellé ; l'INBOX garde le libellé "INBOX" (vue Boîte de réception).

Mapping :
- gmail_id   = "{folder}\\x1f{uidvalidity}\\x1f{uid}" (unique par dossier ; le
  dossier + l'UID sont récupérables via imap_client.parse_imap_key).
- label_ids  = [nom du dossier] (+ "UNREAD" si le flag \\Seen est absent).
- thread_id  = Message-ID (pas de fil IMAP).

Le client est injecté (testable sans réseau).
"""
from __future__ import annotations
import json
from core.rfc822_parse import parse_rfc822
from core.imap_client import imap_msg_key, ImapError


def _label_display(folder: str) -> str:
    if folder == "INBOX":
        return "INBOX"
    for sep in (".", "/"):
        if sep in folder:
            return folder.rsplit(sep, 1)[-1]
    return folder


class ImapSyncer:
    def __init__(self, store, client, account_id, backfill_months: int = 12):
        self.store = store
        self.client = client
        self.account_id = account_id
        # backfill_months : gardé pour compat de signature (Orange charge tout).

    def _val_key(self, folder):
        return f"imap:{folder}:uidvalidity"

    def _uid_key(self, folder):
        return f"imap:{folder}:last_uid"

    def _store_one(self, folder, uidvalidity, uid, raw, seen):
        fields, atts = parse_rfc822(raw)
        fields["label_ids"] = json.dumps([folder] if seen else [folder, "UNREAD"])
        fields["is_unread"] = 0 if seen else 1
        mid = self.store.upsert_message(
            self.account_id, imap_msg_key(folder, uidvalidity, uid), **fields)
        self.store.replace_attachments(mid, atts)

    def _refresh_labels(self, folders):
        self.store.replace_labels(self.account_id, [
            {"id": f, "name": _label_display(f),
             "type": "system" if f == "INBOX" else "user"}
            for f in folders
        ])

    def _fetch_and_store(self, folder, uidvalidity, uids):
        count = 0
        for uid in uids:
            raw, seen = self.client.fetch(uid)
            self._store_one(folder, uidvalidity, uid, raw, seen)
            count += 1
        if uids:
            self.store.set_sync_state(self.account_id, self._uid_key(folder), max(uids))
        return count

    def _folder_full(self, folder):
        uidvalidity = self.client.select_folder(folder)
        self.store.set_sync_state(self.account_id, self._val_key(folder), uidvalidity)
        return self._fetch_and_store(folder, uidvalidity, self.client.search_uids())

    def _folder_incremental(self, folder):
        uidvalidity = self.client.select_folder(folder)
        stored = self.store.get_sync_state(self.account_id, self._val_key(folder))
        if stored is None or str(stored) != str(uidvalidity):
            self.store.set_sync_state(self.account_id, self._val_key(folder), uidvalidity)
            return self._fetch_and_store(folder, uidvalidity, self.client.search_uids())
        last_uid = int(self.store.get_sync_state(self.account_id, self._uid_key(folder)) or 0)
        uids = [u for u in self.client.search_uids(min_uid=last_uid + 1) if u > last_uid]
        return self._fetch_and_store(folder, uidvalidity, uids)

    def _run_all(self, per_folder) -> int:
        self.client.connect()
        try:
            folders = self.client.list_folders()
            self._refresh_labels(folders)
            total = 0
            for f in folders:
                try:
                    total += per_folder(f)
                except ImapError:
                    continue          # dossier illisible : on passe au suivant
            return total
        finally:
            self.client.logout()

    def backfill(self) -> int:
        total = self._run_all(self._folder_full)
        self.store.set_sync_state(self.account_id, "backfill_done", "1")
        return total

    def incremental(self) -> int:
        return self._run_all(self._folder_incremental)
