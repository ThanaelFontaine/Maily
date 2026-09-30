import pytest
from core.store import Store


@pytest.fixture
def store(database):
    return Store(database)


def test_upsert_account_is_idempotent(store):
    a1 = store.upsert_account("me@example.com", display_name="Moi")
    a2 = store.upsert_account("me@example.com", display_name="Moi 2")
    assert a1 == a2
    accounts = store.list_accounts()
    assert len(accounts) == 1
    assert accounts[0]["display_name"] == "Moi 2"


def test_upsert_message_and_get(store):
    acc = store.upsert_account("me@example.com")
    mid = store.upsert_message(acc, "gmail-1", subject="Sujet", body_text="bonjour monde", addr_from="x@y.co")
    row = store.get_message(mid)
    assert row["subject"] == "Sujet"
    mid2 = store.upsert_message(acc, "gmail-1", subject="Sujet edite")
    assert mid == mid2
    assert store.get_message(mid)["subject"] == "Sujet edite"


def test_search_messages_fts(store):
    acc = store.upsert_account("me@example.com")
    store.upsert_message(acc, "g1", subject="Candidature", body_text="reponse du recruteur", addr_from="rh@boite.co")
    store.upsert_message(acc, "g2", subject="Facture", body_text="paiement stripe", addr_from="billing@example.com")
    hits = store.search_messages("recruteur")
    assert len(hits) == 1
    assert hits[0]["gmail_id"] == "g1"


def test_sync_state_roundtrip(store):
    acc = store.upsert_account("me@example.com")
    store.set_sync_state(acc, "last_history_id", "12345")
    assert store.get_sync_state(acc, "last_history_id") == "12345"
    assert store.get_sync_state(acc, "absent") is None


def test_delete_account_removes_account_and_cache(store):
    acc = store.upsert_account("me@example.com")
    other = store.upsert_account("autre@example.com")
    mid = store.upsert_message(acc, "g1", subject="Secret", body_text="corps",
                               label_ids='["INBOX"]', addr_from="x@y.co")
    store.replace_attachments(mid, [{"filename": "f.pdf", "mime_type": "application/pdf",
                                     "size": 3, "gmail_attachment_id": "a1", "content_id": None}])
    store.replace_labels(acc, [{"id": "INBOX", "name": "INBOX", "type": "system"}])
    store.set_sync_state(acc, "last_history_id", "42")
    # message chez l'autre compte, ne doit PAS disparaitre
    store.upsert_message(other, "g2", subject="Garde", body_text="reste", addr_from="z@y.co")

    store.delete_account(acc)

    assert store.get_account(acc) is None
    assert store.list_messages(acc) == []
    assert store.list_labels(acc) == []
    assert store.get_sync_state(acc, "last_history_id") is None
    assert store.list_attachments(mid) == []
    assert store.search_messages("Secret") == []          # FTS nettoye
    # l'autre compte est intact
    assert store.get_account(other) is not None
    assert len(store.list_messages(other)) == 1
    assert store.search_messages("Garde")[0]["gmail_id"] == "g2"
