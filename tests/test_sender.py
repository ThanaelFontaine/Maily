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
    acc = store.upsert_account("me@example.com")
    client = FakeClient()
    res = sender.send_message(store, client, acc, "me@example.com", "d@example.com", "Sujet", "corps")
    assert res["gmail_id"] == "g999"
    ob = store.get_outbox(res["outbox_id"])
    assert ob["status"] == "sent" and ob["gmail_id"] == "g999"
    assert client.sent is not None


def test_send_failure_marks_failed(store):
    acc = store.upsert_account("me@example.com")
    client = FakeClient(fail=True)
    with pytest.raises(RuntimeError):
        sender.send_message(store, client, acc, "me@example.com", "d@example.com", "S", "c")
    row = store.db.read().execute("SELECT status, error FROM outbox").fetchone()
    assert row["status"] == "failed" and "boom" in row["error"]


def test_send_from_account_decodes_attachments(store, monkeypatch):
    import base64
    from core import accounts_service as svc
    acc = store.upsert_account("me@example.com")
    captured = {}

    class FakeClient2:
        def send(self, raw, thread_id=None):
            captured["raw"] = raw
            return {"id": "g1"}

    monkeypatch.setattr(svc, "build_gmail_client", lambda e: FakeClient2())
    payload = {"to": "d@example.com", "subject": "S", "body_text": "c",
               "attachments": [{"filename": "a.txt", "mime_type": "text/plain",
                                "data": base64.b64encode(b"hi").decode()}]}
    res = svc.send_from_account(store, "me@example.com", acc, payload)
    assert res["gmail_id"] == "g1"
    decoded = base64.urlsafe_b64decode(captured["raw"]).decode(errors="ignore")
    assert "a.txt" in decoded


def test_idempotency_dedup(store):
    acc = store.upsert_account("me@example.com")

    class Counting:
        def __init__(self):
            self.n = 0

        def send(self, raw, thread_id=None):
            self.n += 1
            return {"id": "g%d" % self.n}

    client = Counting()
    r1 = sender.send_message(store, client, acc, "me@x.co", "d@example.com", "S", "b", idempotency_key="K")
    r2 = sender.send_message(store, client, acc, "me@x.co", "d@example.com", "S", "b", idempotency_key="K")
    assert client.n == 1  # deuxieme appel dedupe, aucun re-envoi
    assert r2.get("deduped") is True
    assert r1["outbox_id"] == r2["outbox_id"]


def test_send_from_account_size_guard(store, monkeypatch):
    import base64
    from core import accounts_service as svc
    monkeypatch.setattr(svc, "_MAX_SEND_BYTES", 3)
    monkeypatch.setattr(svc, "build_gmail_client", lambda e: None)
    acc = store.upsert_account("me@example.com")
    payload = {"to": "d@example.com", "attachments": [{"filename": "b", "mime_type": "x/y",
               "data": base64.b64encode(b"toolong").decode()}]}
    with pytest.raises(ValueError):
        svc.send_from_account(store, "me@example.com", acc, payload)
