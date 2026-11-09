"""IMAP sync into the local store, reusing the Gmail schema.

IMAP imports **everything**: every IMAP folder, without a date limit. Each
folder becomes a label; INBOX keeps the "INBOX" label (Inbox view).

Mapping:
- gmail_id   = "{folder}\\x1f{uidvalidity}\\x1f{uid}" (unique per folder; the
  folder and the UID can be read back with imap_client.parse_imap_key).
- label_ids  = [folder name] (+ "UNREAD" when the \\Seen flag is absent).
- thread_id  = Message-ID (IMAP has no threads).

The client is injected (testable without network).
"""
from __future__ import annotations
import json
from core.rfc822_parse import parse_rfc822_safe, UNREADABLE_LABEL
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
        # backfill_months: kept for signature compatibility (IMAP loads everything).

    def _val_key(self, folder):
        return f"imap:{folder}:uidvalidity"

    def _uid_key(self, folder):
        return f"imap:{folder}:last_uid"

    def _store_one(self, folder, uidvalidity, uid, raw, seen):
        fields, atts, readable = parse_rfc822_safe(raw)
        labels = [folder] if seen else [folder, "UNREAD"]
        if not readable:
            labels.append(UNREADABLE_LABEL)
        fields["label_ids"] = json.dumps(labels)
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
        # UIDs in ascending order, resume point saved after each message: a network error
        # (ImapError, OSError) raised by `fetch` leaves last_uid on the last message stored,
        # so the next sync resumes there and skips nothing. A message the parser cannot read
        # never raises here: it is stored as a placeholder card (parse_rfc822_safe).
        count = 0
        for uid in sorted(uids):
            raw, seen = self.client.fetch(uid)
            self._store_one(folder, uidvalidity, uid, raw, seen)
            self.store.set_sync_state(self.account_id, self._uid_key(folder), uid)
            count += 1
        return count

    def _reset_folder(self, folder, uidvalidity):
        """New UIDVALIDITY: the old UIDs mean nothing, restart this folder from zero."""
        self.store.set_sync_state(self.account_id, self._uid_key(folder), 0)
        self.store.set_sync_state(self.account_id, self._val_key(folder), uidvalidity)

    def _folder_full(self, folder):
        uidvalidity = self.client.select_folder(folder)
        self._reset_folder(folder, uidvalidity)
        return self._fetch_and_store(folder, uidvalidity, self.client.search_uids())

    def _folder_incremental(self, folder):
        uidvalidity = self.client.select_folder(folder)
        stored = self.store.get_sync_state(self.account_id, self._val_key(folder))
        if stored is None or str(stored) != str(uidvalidity):
            self._reset_folder(folder, uidvalidity)
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
                    continue          # unreadable folder: move on to the next one
            return total
        finally:
            self.client.logout()

    def backfill(self) -> int:
        total = self._run_all(self._folder_full)
        self.store.set_sync_state(self.account_id, "backfill_done", "1")
        return total

    def incremental(self) -> int:
        return self._run_all(self._folder_incremental)
