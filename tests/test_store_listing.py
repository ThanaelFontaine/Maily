import pytest
from core.store import Store


@pytest.fixture
def store(database):
    return Store(database)


def _seed(store):
    a = store.upsert_account("me@example.com")
    b = store.upsert_account("personal@example.org")
    store.upsert_message(a, "g1", thread_id="t1", subject="One", internal_date=100, label_ids='["INBOX"]')
    store.upsert_message(a, "g2", thread_id="t1", subject="One-reply", internal_date=200, label_ids='["INBOX"]')
    store.upsert_message(b, "g3", thread_id="t2", subject="Two", internal_date=300, label_ids='["INBOX","IMPORTANT"]')
    store.upsert_message(a, "g4", thread_id="t3", subject="Trashed", internal_date=400, is_trashed=1)
    return a, b


def test_list_messages_unified_excludes_trash(store):
    _seed(store)
    msgs = store.list_messages()
    subjects = [m["subject"] for m in msgs]
    assert "Trashed" not in subjects
    assert subjects[0] == "Two"


def test_list_messages_per_account(store):
    a, b = _seed(store)
    msgs = store.list_messages(account_id=b)
    assert {m["subject"] for m in msgs} == {"Two"}


def test_list_messages_require_label(store):
    _seed(store)
    msgs = store.list_messages(require_labels=["IMPORTANT"])
    assert {m["subject"] for m in msgs} == {"Two"}


def test_list_messages_exclude_label(store):
    _seed(store)
    msgs = store.list_messages(require_labels=["INBOX"], exclude_labels=["IMPORTANT"])
    subjects = {m["subject"] for m in msgs}
    assert "Two" not in subjects and "One" in subjects


def test_labels_replace_and_list(store):
    acc = store.upsert_account("me@example.com")
    store.replace_labels(acc, [{"id": "Label_1", "name": "Personal", "type": "user"},
                               {"id": "INBOX", "name": "INBOX", "type": "system"}])
    labs = store.list_labels(acc)
    assert {l["name"] for l in labs} == {"Personal", "INBOX"}
    store.replace_labels(acc, [{"id": "Label_1", "name": "Personal", "type": "user"}])
    assert len(store.list_labels(acc)) == 1


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


def test_threads_no_cross_account_merge(store):
    a = store.upsert_account("a@example.com")
    b = store.upsert_account("b@example.com")
    store.upsert_message(a, "g1", thread_id="shared", subject="A subj", internal_date=100, label_ids='["INBOX"]')
    store.upsert_message(b, "g2", thread_id="shared", subject="B subj", internal_date=200, label_ids='["INBOX"]')
    shared = [t for t in store.list_threads() if t["thread_id"] == "shared"]
    assert len(shared) == 2
    assert {t["subject"] for t in shared} == {"A subj", "B subj"}
    assert all(t["message_count"] == 1 for t in shared)


def test_mark_trashed_by_gmail_id(store):
    a = store.upsert_account("a@example.com")
    store.upsert_message(a, "g1")
    assert store.mark_trashed_by_gmail_id(a, "g1") is True
    assert store.list_messages(trashed=True)[0]["gmail_id"] == "g1"
    assert store.mark_trashed_by_gmail_id(a, "ghost") is False


def test_replace_attachments_preserves_local_path(store):
    a = store.upsert_account("a@example.com")
    mid = store.upsert_message(a, "g1")
    att = {"filename": "c.pdf", "mime_type": "application/pdf", "size": 1, "gmail_attachment_id": "att1", "content_id": None}
    store.replace_attachments(mid, [att])
    att_id = store.list_attachments(mid)[0]["id"]
    store.set_attachment_path(att_id, "/tmp/x.pdf")
    store.replace_attachments(mid, [att])
    assert store.list_attachments(mid)[0]["local_path"] == "/tmp/x.pdf"
