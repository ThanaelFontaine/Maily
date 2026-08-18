import pytest
from core.store import Store


@pytest.fixture
def store(database):
    return Store(database)


def test_upsert_account_is_idempotent(store):
    a1 = store.upsert_account("me@example.org", display_name="Moi")
    a2 = store.upsert_account("me@example.org", display_name="Moi 2")
    assert a1 == a2
    accounts = store.list_accounts()
    assert len(accounts) == 1
    assert accounts[0]["display_name"] == "Moi 2"


def test_upsert_message_and_get(store):
    acc = store.upsert_account("me@example.org")
    mid = store.upsert_message(acc, "gmail-1", subject="Sujet", body_text="bonjour monde", addr_from="x@y.co")
    row = store.get_message(mid)
    assert row["subject"] == "Sujet"
    mid2 = store.upsert_message(acc, "gmail-1", subject="Sujet edite")
    assert mid == mid2
    assert store.get_message(mid)["subject"] == "Sujet edite"


def test_search_messages_fts(store):
    acc = store.upsert_account("me@example.org")
    store.upsert_message(acc, "g1", subject="Candidature", body_text="reponse du recruteur", addr_from="rh@boite.co")
    store.upsert_message(acc, "g2", subject="Facture", body_text="paiement stripe", addr_from="no@stripe.com")
    hits = store.search_messages("recruteur")
    assert len(hits) == 1
    assert hits[0]["gmail_id"] == "g1"


def test_sync_state_roundtrip(store):
    acc = store.upsert_account("me@example.org")
    store.set_sync_state(acc, "last_history_id", "12345")
    assert store.get_sync_state(acc, "last_history_id") == "12345"
    assert store.get_sync_state(acc, "absent") is None
