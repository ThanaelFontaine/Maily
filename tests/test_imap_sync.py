import json
from email.message import EmailMessage
from core.db import Database
from core.store import Store
from core.imap_sync import ImapSyncer


def _raw(subject, body="corps"):
    m = EmailMessage()
    m["From"] = "a@orange.fr"
    m["To"] = "me@orange.fr"
    m["Subject"] = subject
    m["Message-ID"] = f"<{subject}@orange.fr>"
    m["Date"] = "Mon, 18 Aug 2025 10:30:00 +0200"
    m.set_content(body)
    return m.as_bytes()


class FakeImap:
    def __init__(self, messages, uidvalidity=1000):
        # messages : {uid: (raw_bytes, seen)}
        self.messages = messages
        self.uidvalidity = uidvalidity
        self.trashed = []
        self.logged_out = False

    def connect(self):
        return self

    def select_inbox(self):
        return self.uidvalidity

    def search_uids(self, since=None, min_uid=None):
        uids = sorted(self.messages)
        if min_uid is not None:
            uids = [u for u in uids if u >= min_uid]
        return uids

    def fetch(self, uid):
        return self.messages[uid]

    def move_to_trash(self, uid):
        self.trashed.append(uid)

    def logout(self):
        self.logged_out = True


def test_backfill_imports_inbox(tmp_path):
    db = Database(tmp_path / "app.sqlite")
    store = Store(db)
    aid = store.upsert_account("me@orange.fr", provider="imap")
    client = FakeImap({1: (_raw("Un"), True), 2: (_raw("Deux"), False)})
    n = ImapSyncer(store, client, aid).backfill()
    assert n == 2
    msgs = store.list_messages(aid, require_labels=["INBOX"])
    subjects = {m["subject"] for m in msgs}
    assert subjects == {"Un", "Deux"}
    # flag \Seen -> is_unread ; label synthetique INBOX/UNREAD
    by_subj = {m["subject"]: m for m in msgs}
    assert by_subj["Un"]["is_unread"] == 0
    assert by_subj["Deux"]["is_unread"] == 1
    assert "UNREAD" in json.loads(by_subj["Deux"]["label_ids"])
    # gmail_id = uidvalidity.uid
    assert by_subj["Un"]["gmail_id"] == "1000.1"
    assert store.get_sync_state(aid, "backfill_done") == "1"
    assert store.get_sync_state(aid, "imap_last_uid") == "2"
    assert client.logged_out is True
    db.close()


def test_incremental_fetches_only_new(tmp_path):
    db = Database(tmp_path / "app.sqlite")
    store = Store(db)
    aid = store.upsert_account("me@orange.fr", provider="imap")
    client = FakeImap({1: (_raw("Un"), True)})
    ImapSyncer(store, client, aid).backfill()
    # nouveau message arrive
    client.messages[2] = (_raw("Nouveau"), False)
    n = ImapSyncer(store, client, aid).incremental()
    assert n == 1
    msgs = {m["subject"] for m in store.list_messages(aid, require_labels=["INBOX"])}
    assert msgs == {"Un", "Nouveau"}
    assert store.get_sync_state(aid, "imap_last_uid") == "2"
    db.close()


def test_uidvalidity_change_triggers_full_reimport(tmp_path):
    db = Database(tmp_path / "app.sqlite")
    store = Store(db)
    aid = store.upsert_account("me@orange.fr", provider="imap")
    client = FakeImap({1: (_raw("Un"), True)}, uidvalidity=1000)
    ImapSyncer(store, client, aid).backfill()
    # la boite reinitialise ses UID (uidvalidity change)
    client.uidvalidity = 2000
    client.messages = {1: (_raw("Reimport"), True)}
    n = ImapSyncer(store, client, aid).incremental()
    assert n == 1
    ids = {m["gmail_id"] for m in store.list_messages(aid, require_labels=["INBOX"])}
    assert "2000.1" in ids
    db.close()
