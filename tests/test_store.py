import pytest
from core.store import Store


@pytest.fixture
def store(database):
    return Store(database)


def test_upsert_account_is_idempotent(store):
    a1 = store.upsert_account("me@example.com", display_name="Me")
    a2 = store.upsert_account("me@example.com", display_name="Me 2")
    assert a1 == a2
    accounts = store.list_accounts()
    assert len(accounts) == 1
    assert accounts[0]["display_name"] == "Me 2"


def test_upsert_message_and_get(store):
    acc = store.upsert_account("me@example.com")
    mid = store.upsert_message(acc, "gmail-1", subject="Subject", body_text="hello world", addr_from="x@example.org")
    row = store.get_message(mid)
    assert row["subject"] == "Subject"
    mid2 = store.upsert_message(acc, "gmail-1", subject="Subject edited")
    assert mid == mid2
    assert store.get_message(mid)["subject"] == "Subject edited"


def test_search_messages_fts(store):
    acc = store.upsert_account("me@example.com")
    store.upsert_message(acc, "g1", subject="Application", body_text="reply from the recruiter", addr_from="rh@example.org")
    store.upsert_message(acc, "g2", subject="Invoice", body_text="card payment receipt", addr_from="billing@example.com")
    hits = store.search_messages("recruiter")
    assert len(hits) == 1
    assert hits[0]["gmail_id"] == "g1"


def test_sync_state_roundtrip(store):
    acc = store.upsert_account("me@example.com")
    store.set_sync_state(acc, "last_history_id", "12345")
    assert store.get_sync_state(acc, "last_history_id") == "12345"
    assert store.get_sync_state(acc, "missing") is None


def test_delete_account_removes_account_and_cache(store):
    acc = store.upsert_account("me@example.com")
    other = store.upsert_account("other@example.com")
    mid = store.upsert_message(acc, "g1", subject="Secret", body_text="body",
                               label_ids='["INBOX"]', addr_from="x@example.org")
    store.replace_attachments(mid, [{"filename": "f.pdf", "mime_type": "application/pdf",
                                     "size": 3, "gmail_attachment_id": "a1", "content_id": None}])
    store.replace_labels(acc, [{"id": "INBOX", "name": "INBOX", "type": "system"}])
    store.set_sync_state(acc, "last_history_id", "42")
    # message of the other account, must NOT disappear
    store.upsert_message(other, "g2", subject="Keep", body_text="stays", addr_from="z@example.org")

    store.delete_account(acc)

    assert store.get_account(acc) is None
    assert store.list_messages(acc) == []
    assert store.list_labels(acc) == []
    assert store.get_sync_state(acc, "last_history_id") is None
    assert store.list_attachments(mid) == []
    assert store.search_messages("Secret") == []          # FTS nettoye
    # the other account is intact
    assert store.get_account(other) is not None
    assert len(store.list_messages(other)) == 1
    assert store.search_messages("Keep")[0]["gmail_id"] == "g2"
