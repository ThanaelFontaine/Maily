import pytest
from core.store import Store
from core.sync import Syncer
from core.gmail import HistoryExpired


def _msg(gid, subject, labels=None, hist="10"):
    return {
        "id": gid, "threadId": "t-" + gid, "snippet": "s", "internalDate": "1700000000000",
        "historyId": hist, "labelIds": labels or ["INBOX"],
        "payload": {"mimeType": "text/plain",
                    "headers": [{"name": "Subject", "value": subject}],
                    "body": {"data": ""}},
    }


class FakeClient:
    def __init__(self, messages, history=None, history_raises=False):
        self.messages = messages
        self.history = history or []
        self.history_raises = history_raises

    def list_message_ids(self, query=None, page_token=None, max_results=100):
        return list(self.messages.keys()), None

    def get_message(self, gid, fmt="full"):
        return self.messages[gid]

    def list_history(self, start_history_id, page_token=None):
        if self.history_raises:
            raise HistoryExpired("too old")
        return self.history, None, "999"


@pytest.fixture
def store(database):
    return Store(database)


def test_backfill_imports_messages(store):
    acc = store.upsert_account("me@example.org")
    client = FakeClient({"g1": _msg("g1", "Un"), "g2": _msg("g2", "Deux")})
    n = Syncer(store, client, acc).backfill()
    assert n == 2
    assert store.get_sync_state(acc, "backfill_done") == "1"
    assert store.get_sync_state(acc, "last_history_id") == "10"
    assert len(store.search_messages("Deux")) == 1


def test_incremental_adds_and_trashes(store):
    acc = store.upsert_account("me@example.org")
    Syncer(store, FakeClient({"g1": _msg("g1", "Un")}), acc).backfill()
    hist = [
        {"id": "11", "messagesAdded": [{"message": {"id": "g2"}}]},
        {"id": "12", "messagesDeleted": [{"message": {"id": "g1"}}]},
    ]
    client = FakeClient({"g1": _msg("g1", "Un"), "g2": _msg("g2", "Deux")}, history=hist)
    n = Syncer(store, client, acc).incremental()
    assert n == 2
    assert store.get_sync_state(acc, "last_history_id") == "999"
    g1 = store.db.read().execute("SELECT is_trashed FROM messages WHERE gmail_id='g1'").fetchone()
    assert g1["is_trashed"] == 1


def test_incremental_resyncs_on_history_expired(store):
    acc = store.upsert_account("me@example.org")
    Syncer(store, FakeClient({"g1": _msg("g1", "Un")}), acc).backfill()
    client = FakeClient({"g1": _msg("g1", "Un"), "g9": _msg("g9", "Neuf")}, history_raises=True)
    Syncer(store, client, acc).incremental()
    assert store.search_messages("Neuf")


class PagedClient(FakeClient):
    """Deux pages d'historique ; la seconde peut tomber en panne (quota Gmail)."""

    def __init__(self, messages, pages, panne_page2=False):
        super().__init__(messages)
        self.pages = pages
        self.panne_page2 = panne_page2
        self.relectures = []

    def get_message(self, gid, fmt="full"):
        self.relectures.append(gid)
        return self.messages[gid]

    def list_history(self, start_history_id, page_token=None):
        if page_token is None:
            return self.pages[0], "p2", "999"
        if self.panne_page2:
            raise RuntimeError("quota")
        return self.pages[1], None, "999"


def test_incremental_checkpoints_each_page_so_a_failure_does_not_restart_from_scratch(store):
    acc = store.upsert_account("me@example.org")
    Syncer(store, FakeClient({"g1": _msg("g1", "Un")}), acc).backfill()
    pages = [[{"id": "11", "messagesAdded": [{"message": {"id": "g2"}}]}], [{"id": "12", "messagesAdded": [{"message": {"id": "g3"}}]}]]
    msgs = {"g1": _msg("g1", "Un"), "g2": _msg("g2", "Deux"), "g3": _msg("g3", "Trois")}
    with pytest.raises(RuntimeError):
        Syncer(store, PagedClient(msgs, pages, panne_page2=True), acc).incremental()
    assert store.get_sync_state(acc, "last_history_id") == "11"
    assert store.search_messages("Deux")
    Syncer(store, PagedClient(msgs, pages), acc).incremental()
    assert store.get_sync_state(acc, "last_history_id") == "999"
    assert store.search_messages("Trois")


def test_incremental_refetches_a_message_once_per_run(store):
    acc = store.upsert_account("me@example.org")
    Syncer(store, FakeClient({"g1": _msg("g1", "Un")}), acc).backfill()
    pages = [
        [{"id": "11", "messagesAdded": [{"message": {"id": "g2"}}]}, {"id": "12", "labelsAdded": [{"message": {"id": "g2"}}]}],
        [{"id": "13", "labelsRemoved": [{"message": {"id": "g2"}}]}],
    ]
    client = PagedClient({"g1": _msg("g1", "Un"), "g2": _msg("g2", "Deux")}, pages)
    Syncer(store, client, acc).incremental()
    assert client.relectures == ["g2"]
