import json
from email.message import EmailMessage
from core.db import Database
from core.store import Store
from core.imap_sync import ImapSyncer
from core.imap_client import parse_imap_key


def _raw(subject, body="corps"):
    m = EmailMessage()
    m["From"] = "a@example.net"
    m["To"] = "me@example.net"
    m["Subject"] = subject
    m["Message-ID"] = f"<{subject}@example.net>"
    m["Date"] = "Mon, 18 Aug 2025 10:30:00 +0200"
    m.set_content(body)
    return m.as_bytes()


class FakeImap:
    """Multi-dossiers : folders = {name: {"uidvalidity": int, "messages": {uid:(raw,seen)}}}."""
    def __init__(self, folders):
        self.folders = folders
        self.selected = None
        self.trashed = []
        self.logged_out = False

    def connect(self):
        return self

    def list_folders(self):
        return list(self.folders)

    def select_folder(self, name):
        self.selected = name
        return self.folders[name]["uidvalidity"]

    def search_uids(self, since=None, min_uid=None):
        uids = sorted(self.folders[self.selected]["messages"])
        if min_uid is not None:
            uids = [u for u in uids if u >= min_uid]
        return uids

    def fetch(self, uid):
        return self.folders[self.selected]["messages"][uid]

    def move_to_trash(self, uid):
        self.trashed.append((self.selected, uid))

    def logout(self):
        self.logged_out = True


def _mk(tmp_path):
    db = Database(tmp_path / "app.sqlite")
    store = Store(db)
    aid = store.upsert_account("me@example.net", provider="imap")
    return db, store, aid


def test_backfill_imports_all_folders_no_date_limit(tmp_path):
    db, store, aid = _mk(tmp_path)
    client = FakeImap({
        "INBOX": {"uidvalidity": 10, "messages": {1: (_raw("Recu1"), True),
                                                  2: (_raw("Recu2"), False)}},
        "INBOX.Sent": {"uidvalidity": 20, "messages": {5: (_raw("Envoye1"), True)}},
        "Archive2019": {"uidvalidity": 30, "messages": {9: (_raw("Vieux2019"), True)}},
    })
    n = ImapSyncer(store, client, aid).backfill()
    assert n == 4                                   # tous dossiers, tout âge
    all_msgs = store.list_messages(aid)             # sans filtre de label
    subjects = {m["subject"] for m in all_msgs}
    assert subjects == {"Recu1", "Recu2", "Envoye1", "Vieux2019"}

    # INBOX -> label INBOX ; autres dossiers -> label = nom du dossier
    by_subj = {m["subject"]: m for m in all_msgs}
    assert json.loads(by_subj["Recu1"]["label_ids"]) == ["INBOX"]
    assert "INBOX.Sent" in json.loads(by_subj["Envoye1"]["label_ids"])
    assert "Archive2019" in json.loads(by_subj["Vieux2019"]["label_ids"])

    # la vue "Boîte de réception" (require INBOX) ne montre que l'INBOX
    inbox = {m["subject"] for m in store.list_messages(aid, require_labels=["INBOX"])}
    assert inbox == {"Recu1", "Recu2"}

    # les dossiers apparaissent comme libellés (INBOX en 'system', les autres en 'user')
    labels = {l["gmail_label_id"]: l["type"] for l in store.list_labels(aid)}
    assert labels["INBOX"] == "system"
    assert labels["INBOX.Sent"] == "user"
    assert labels["Archive2019"] == "user"

    # gmail_id encode le dossier -> (folder, uid) récupérables
    folder, uid = parse_imap_key(by_subj["Envoye1"]["gmail_id"])
    assert folder == "INBOX.Sent" and uid == 5
    assert client.logged_out is True
    db.close()


def test_incremental_only_new_per_folder(tmp_path):
    db, store, aid = _mk(tmp_path)
    client = FakeImap({"INBOX": {"uidvalidity": 10, "messages": {1: (_raw("A"), True)}}})
    ImapSyncer(store, client, aid).backfill()
    client.folders["INBOX"]["messages"][2] = (_raw("B"), False)
    n = ImapSyncer(store, client, aid).incremental()
    assert n == 1
    assert {m["subject"] for m in store.list_messages(aid, require_labels=["INBOX"])} == {"A", "B"}
    db.close()


def test_uidvalidity_change_reimports_folder(tmp_path):
    db, store, aid = _mk(tmp_path)
    client = FakeImap({"INBOX": {"uidvalidity": 10, "messages": {1: (_raw("Un"), True)}}})
    ImapSyncer(store, client, aid).backfill()
    client.folders["INBOX"]["uidvalidity"] = 99
    client.folders["INBOX"]["messages"] = {1: (_raw("Reimport"), True)}
    n = ImapSyncer(store, client, aid).incremental()
    assert n == 1
    ids = {m["gmail_id"] for m in store.list_messages(aid, require_labels=["INBOX"])}
    assert any("99" in k for k in ids)
    db.close()
