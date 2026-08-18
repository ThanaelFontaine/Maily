import pytest
from core.store import Store
from core import sender


@pytest.fixture
def store(database):
    return Store(database)


class FakeClient:
    def __init__(self, fail=False):
        self.fail = fail
        self.sent = None

    def send(self, raw, thread_id=None):
        if self.fail:
            raise RuntimeError("boom")
        self.sent = (raw, thread_id)
        return {"id": "g999"}


def test_send_success(store):
    acc = store.upsert_account("me@example.org")
    client = FakeClient()
    res = sender.send_message(store, client, acc, "me@example.org", "d@x.co", "Sujet", "corps")
    assert res["gmail_id"] == "g999"
    ob = store.get_outbox(res["outbox_id"])
    assert ob["status"] == "sent" and ob["gmail_id"] == "g999"
    assert client.sent is not None


def test_send_failure_marks_failed(store):
    acc = store.upsert_account("me@example.org")
    client = FakeClient(fail=True)
    with pytest.raises(RuntimeError):
        sender.send_message(store, client, acc, "me@example.org", "d@x.co", "S", "c")
    row = store.db.read().execute("SELECT status, error FROM outbox").fetchone()
    assert row["status"] == "failed" and "boom" in row["error"]
