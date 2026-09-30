import json
import pytest
from core.store import Store
from core import accounts_service as svc


@pytest.fixture
def store(database):
    return Store(database)


def test_apply_local_labels(store):
    acc = store.upsert_account("me@example.com")
    mid = store.upsert_message(acc, "g1", label_ids='["INBOX","UNREAD"]', is_unread=1)
    store.apply_local_labels(mid, remove=["UNREAD"])
    m = store.get_message(mid)
    assert m["is_unread"] == 0
    assert "UNREAD" not in json.loads(m["label_ids"])
    store.apply_local_labels(mid, add=["STARRED"])
    assert store.get_message(mid)["is_starred"] == 1


def test_set_trashed(store):
    acc = store.upsert_account("me@example.com")
    mid = store.upsert_message(acc, "g1")
    store.set_trashed(mid, True)
    assert store.get_message(mid)["is_trashed"] == 1


class FakeClient:
    def __init__(self):
        self.calls = []

    def modify(self, gid, add=None, remove=None):
        self.calls.append(("modify", gid, add, remove))

    def trash(self, gid):
        self.calls.append(("trash", gid))

    def untrash(self, gid):
        self.calls.append(("untrash", gid))


def test_modify_message_updates_local(store, monkeypatch):
    acc = store.upsert_account("me@example.com")
    mid = store.upsert_message(acc, "g1", label_ids='["INBOX","UNREAD"]', is_unread=1)
    fc = FakeClient()
    monkeypatch.setattr(svc, "build_gmail_client", lambda e: fc)
    svc.modify_message(store, "me@example.com", mid, remove=["UNREAD"])
    assert ("modify", "g1", None, ["UNREAD"]) in fc.calls
    assert store.get_message(mid)["is_unread"] == 0


def test_trash_message_updates_local(store, monkeypatch):
    acc = store.upsert_account("me@example.com")
    mid = store.upsert_message(acc, "g1")
    fc = FakeClient()
    monkeypatch.setattr(svc, "build_gmail_client", lambda e: fc)
    svc.trash_message(store, "me@example.com", mid)
    assert ("trash", "g1") in fc.calls
    assert store.get_message(mid)["is_trashed"] == 1
