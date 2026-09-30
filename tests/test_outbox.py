import sqlite3
import pytest
from core.store import Store


@pytest.fixture
def store(database):
    return Store(database)


def test_add_and_mark_outbox(store):
    acc = store.upsert_account("me@example.com")
    oid = store.add_outbox(acc, "d@example.com", "Sujet", "corps", None, "<mid1@maily>")
    row = store.get_outbox(oid)
    assert row["status"] == "queued"
    assert row["addr_to"] == "d@example.com"

    store.mark_outbox(oid, "sending")
    assert store.get_outbox(oid)["status"] == "sending"

    store.mark_outbox(oid, "sent", gmail_id="g123")
    row = store.get_outbox(oid)
    assert row["status"] == "sent"
    assert row["gmail_id"] == "g123"
    assert row["sent_at"] is not None


def test_idempotency_key_unique(store):
    acc = store.upsert_account("me@example.com")
    store.add_outbox(acc, "d@example.com", "S", "c", None, "<dup@maily>")
    with pytest.raises(sqlite3.IntegrityError):
        store.add_outbox(acc, "d@example.com", "S", "c", None, "<dup@maily>")
