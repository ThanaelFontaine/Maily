import pytest
from core.store import Store


@pytest.fixture
def store(database):
    return Store(database)


def _seed(store):
    a = store.upsert_account("me@example.org")
    b = store.upsert_account("perso@gmail.com")
    store.upsert_message(a, "g1", thread_id="t1", subject="Un", internal_date=100, label_ids='["INBOX"]')
    store.upsert_message(a, "g2", thread_id="t1", subject="Un-reponse", internal_date=200, label_ids='["INBOX"]')
    store.upsert_message(b, "g3", thread_id="t2", subject="Deux", internal_date=300, label_ids='["INBOX","IMPORTANT"]')
    store.upsert_message(a, "g4", thread_id="t3", subject="Corbeille", internal_date=400, is_trashed=1)
    return a, b


def test_list_messages_unified_excludes_trash(store):
    _seed(store)
    msgs = store.list_messages()
    subjects = [m["subject"] for m in msgs]
    assert "Corbeille" not in subjects
    assert subjects[0] == "Deux"


def test_list_messages_per_account(store):
    a, b = _seed(store)
    msgs = store.list_messages(account_id=b)
    assert {m["subject"] for m in msgs} == {"Deux"}


def test_list_messages_label_filter(store):
    _seed(store)
    msgs = store.list_messages(label="IMPORTANT")
    assert {m["subject"] for m in msgs} == {"Deux"}


def test_list_threads_groups(store):
    _seed(store)
    threads = store.list_threads()
    t1 = [t for t in threads if t["thread_id"] == "t1"][0]
    assert t1["message_count"] == 2
    assert threads[0]["thread_id"] == "t2"


def test_get_thread_messages_chrono(store):
    _seed(store)
    msgs = store.get_thread_messages("t1")
    assert [m["gmail_id"] for m in msgs] == ["g1", "g2"]
