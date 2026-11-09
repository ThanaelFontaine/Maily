import json
from email.message import EmailMessage
from core.db import Database
from core.store import Store
from core.imap_sync import ImapSyncer
from core.imap_client import parse_imap_key


def _raw(subject, body="body"):
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
    assert n == 4                                   # every folder, any age
    all_msgs = store.list_messages(aid)             # no label filter
    subjects = {m["subject"] for m in all_msgs}
    assert subjects == {"Recu1", "Recu2", "Envoye1", "Vieux2019"}

    # INBOX gets the INBOX label; other folders get their folder name as label
    by_subj = {m["subject"]: m for m in all_msgs}
    assert json.loads(by_subj["Recu1"]["label_ids"]) == ["INBOX"]
    assert "INBOX.Sent" in json.loads(by_subj["Envoye1"]["label_ids"])
    assert "Archive2019" in json.loads(by_subj["Vieux2019"]["label_ids"])

    # the "Inbox" view (require INBOX) only shows INBOX
    inbox = {m["subject"] for m in store.list_messages(aid, require_labels=["INBOX"])}
    assert inbox == {"Recu1", "Recu2"}

    # folders show up as labels (INBOX as 'system', the others as 'user')
    labels = {l["gmail_label_id"]: l["type"] for l in store.list_labels(aid)}
    assert labels["INBOX"] == "system"
    assert labels["INBOX.Sent"] == "user"
    assert labels["Archive2019"] == "user"

    # gmail_id encodes the folder: (folder, uid) can be read back
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
    client = FakeImap({"INBOX": {"uidvalidity": 10, "messages": {1: (_raw("One"), True)}}})
    ImapSyncer(store, client, aid).backfill()
    client.folders["INBOX"]["uidvalidity"] = 99
    client.folders["INBOX"]["messages"] = {1: (_raw("Reimport"), True)}
    n = ImapSyncer(store, client, aid).incremental()
    assert n == 1
    ids = {m["gmail_id"] for m in store.list_messages(aid, require_labels=["INBOX"])}
    assert any("99" in k for k in ids)
    db.close()


# --- MAIL-34 lot 2b: a malformed message never blocks the sync ---------------------

import pytest
from core.imap_client import ImapError
from core.rfc822_parse import UNREADABLE_BODY, UNREADABLE_LABEL
from tests.test_rfc822_parse import _bad_charset, _deeply_nested


class FlakyImap(FakeImap):
    """Network failure raised by fetch() for one UID."""
    def __init__(self, folders, fail_uid, exc):
        super().__init__(folders)
        self.fail_uid = fail_uid
        self.exc = exc

    def fetch(self, uid):
        if uid == self.fail_uid:
            raise self.exc
        return super().fetch(uid)


def _by_subject(store, aid):
    return {m["subject"]: m for m in store.list_messages(aid)}


def test_bad_charset_mail_is_displayed(tmp_path):
    db, store, aid = _mk(tmp_path)
    client = FakeImap({"INBOX": {"uidvalidity": 1, "messages": {1: (_bad_charset(), False)}}})
    assert ImapSyncer(store, client, aid).backfill() == 1
    m = _by_subject(store, aid)["Bad charset"]
    assert "world" in m["body_text"]
    assert UNREADABLE_LABEL not in json.loads(m["label_ids"])
    db.close()


def test_nested_mail_becomes_a_marked_fallback_and_the_next_mails_are_synced(tmp_path):
    db, store, aid = _mk(tmp_path)
    client = FakeImap({"INBOX": {"uidvalidity": 1, "messages": {
        1: (_raw("Before"), True),
        2: (_deeply_nested(), False),
        3: (_raw("After"), True),
    }}})
    assert ImapSyncer(store, client, aid).backfill() == 3
    subjects = _by_subject(store, aid)
    assert set(subjects) == {"Before", "Deep", "After"}
    deep = subjects["Deep"]
    assert deep["body_text"] == UNREADABLE_BODY
    assert json.loads(deep["label_ids"]) == ["INBOX", "UNREAD", UNREADABLE_LABEL]
    assert deep["has_attachments"] == 0
    assert UNREADABLE_LABEL not in json.loads(subjects["After"]["label_ids"])
    assert store.get_sync_state(aid, "imap:INBOX:last_uid") == "3"
    assert store.get_sync_state(aid, "backfill_done") == "1"
    # the placeholder is not a folder label
    assert UNREADABLE_LABEL not in {l["gmail_label_id"] for l in store.list_labels(aid)}
    db.close()


def test_a_poison_mail_does_not_come_back_at_every_sync(tmp_path):
    db, store, aid = _mk(tmp_path)
    client = FakeImap({"INBOX": {"uidvalidity": 1, "messages": {1: (_deeply_nested(), False)}}})
    ImapSyncer(store, client, aid).backfill()
    client.folders["INBOX"]["messages"][2] = (_raw("Later"), True)
    assert ImapSyncer(store, client, aid).incremental() == 1
    assert "Later" in _by_subject(store, aid)
    db.close()


def test_uids_are_processed_in_ascending_order(tmp_path):
    db, store, aid = _mk(tmp_path)
    client = FakeImap({"INBOX": {"uidvalidity": 1, "messages": {1: (_raw("A"), True)}}})
    syncer = ImapSyncer(store, client, aid)
    seen = []
    orig = client.fetch
    client.fetch = lambda uid: (seen.append(uid), orig(uid))[1]
    client.folders["INBOX"]["messages"].update({5: (_raw("E"), True), 3: (_raw("C"), True)})
    client.search_uids = lambda since=None, min_uid=None: [5, 1, 3]
    syncer.backfill()
    assert seen == [1, 3, 5]
    db.close()


@pytest.mark.parametrize("exc", [ImapError("connection lost"), OSError("network down")])
def test_network_error_keeps_last_uid_on_the_last_stored_message_and_skips_nothing(tmp_path, exc):
    db, store, aid = _mk(tmp_path)
    msgs = {1: (_raw("M1"), True), 2: (_raw("M2"), True), 3: (_raw("M3"), True)}
    client = FlakyImap({"INBOX": {"uidvalidity": 1, "messages": msgs}}, fail_uid=3, exc=exc)
    if isinstance(exc, OSError):
        with pytest.raises(OSError):
            ImapSyncer(store, client, aid).backfill()
    else:
        ImapSyncer(store, client, aid).backfill()
    assert set(_by_subject(store, aid)) == {"M1", "M2"}
    assert store.get_sync_state(aid, "imap:INBOX:last_uid") == "2"
    # the connection is back: the next sync resumes at UID 3, nothing is skipped
    client.fail_uid = None
    assert ImapSyncer(store, client, aid).incremental() == 1
    assert set(_by_subject(store, aid)) == {"M1", "M2", "M3"}
    db.close()


def test_new_uidvalidity_restarts_the_folder_even_if_the_first_fetch_fails(tmp_path):
    db, store, aid = _mk(tmp_path)
    client = FakeImap({"INBOX": {"uidvalidity": 10, "messages": {
        7: (_raw("Old7"), True), 8: (_raw("Old8"), True)}}})
    ImapSyncer(store, client, aid).backfill()
    assert store.get_sync_state(aid, "imap:INBOX:last_uid") == "8"
    flaky = FlakyImap({"INBOX": {"uidvalidity": 99, "messages": {
        1: (_raw("New1"), True), 2: (_raw("New2"), True)}}}, fail_uid=1, exc=ImapError("down"))
    ImapSyncer(store, flaky, aid).incremental()
    assert store.get_sync_state(aid, "imap:INBOX:last_uid") == "0"
    flaky.fail_uid = None
    assert ImapSyncer(store, flaky, aid).incremental() == 2     # UIDs 1 and 2, not skipped
    assert {"New1", "New2"} <= set(_by_subject(store, aid))
    db.close()
