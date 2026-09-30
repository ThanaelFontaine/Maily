import httplib2
import pytest
from googleapiclient.errors import HttpError
from core.store import Store
from core.sync import Syncer


def _msg(gid, subject="S", labels=None, hist="10"):
    return {
        "id": gid, "threadId": "t-" + gid, "snippet": "s", "internalDate": "1700000000000",
        "historyId": hist, "labelIds": labels or ["INBOX"],
        "payload": {"mimeType": "text/plain", "headers": [{"name": "Subject", "value": subject}], "body": {"data": ""}},
    }


def _404():
    return HttpError(httplib2.Response({"status": 404}), b"gone")


class FakeClient:
    def __init__(self, messages, history=None, missing=None, profile_hist=None):
        self.messages = messages
        self.history = history or []
        self.missing = set(missing or [])
        self.profile_hist = profile_hist

    def list_message_ids(self, query=None, page_token=None, max_results=100):
        return list(self.messages.keys()), None

    def get_message(self, gid, fmt="full"):
        if gid in self.missing:
            raise _404()
        return self.messages[gid]

    def list_history(self, start_history_id, page_token=None):
        return self.history, None, "999"

    def get_profile(self):
        return {"historyId": self.profile_hist} if self.profile_hist else {}


@pytest.fixture
def store(database):
    return Store(database)


def test_incremental_applies_label_changes(store):
    acc = store.upsert_account("me@example.com")
    Syncer(store, FakeClient({"g1": _msg("g1", labels=["INBOX", "UNREAD"])}), acc).backfill()
    updated = {"g1": _msg("g1", labels=["INBOX", "STARRED"])}  # lu + starred cote serveur
    hist = [{"id": "11", "labelsRemoved": [{"message": {"id": "g1"}}]},
            {"id": "12", "labelsAdded": [{"message": {"id": "g1"}}]}]
    Syncer(store, FakeClient(updated, history=hist), acc).incremental()
    row = store.db.read().execute("SELECT is_unread, is_starred FROM messages WHERE gmail_id='g1'").fetchone()
    assert row["is_unread"] == 0 and row["is_starred"] == 1


def test_incremental_trash_via_label(store):
    acc = store.upsert_account("me@example.com")
    Syncer(store, FakeClient({"g1": _msg("g1", labels=["INBOX", "UNREAD"])}), acc).backfill()
    trashed = {"g1": _msg("g1", labels=["TRASH"])}
    hist = [{"id": "11", "labelsAdded": [{"message": {"id": "g1"}}]}]
    Syncer(store, FakeClient(trashed, history=hist), acc).incremental()
    row = store.db.read().execute("SELECT is_trashed FROM messages WHERE gmail_id='g1'").fetchone()
    assert row["is_trashed"] == 1
    assert not store.list_messages(require_labels=["INBOX"])


def test_incremental_skips_deleted_in_flight(store):
    acc = store.upsert_account("me@example.com")
    Syncer(store, FakeClient({"g1": _msg("g1")}), acc).backfill()
    msgs = {"g1": _msg("g1"), "g3": _msg("g3", "Trois")}
    hist = [{"id": "11", "messagesAdded": [{"message": {"id": "g2"}}, {"message": {"id": "g3"}}]}]
    Syncer(store, FakeClient(msgs, history=hist, missing=["g2"]), acc).incremental()
    assert store.search_messages("Trois")
    assert store.get_sync_state(acc, "last_history_id") == "999"  # avance malgre le 404


def test_incremental_delete_unknown_is_noop(store):
    acc = store.upsert_account("me@example.com")
    Syncer(store, FakeClient({"g1": _msg("g1")}), acc).backfill()
    before = store.db.read().execute("SELECT COUNT(*) c FROM messages").fetchone()["c"]
    hist = [{"id": "11", "messagesDeleted": [{"message": {"id": "ghost"}}]}]
    Syncer(store, FakeClient({"g1": _msg("g1")}, history=hist), acc).incremental()
    after = store.db.read().execute("SELECT COUNT(*) c FROM messages").fetchone()["c"]
    assert after == before  # pas de ligne fantome


def test_backfill_empty_mailbox_sets_checkpoint(store):
    acc = store.upsert_account("me@example.com")
    n = Syncer(store, FakeClient({}, profile_hist="500"), acc).backfill()
    assert n == 0
    assert store.get_sync_state(acc, "last_history_id") == "500"
