import pytest
from fastapi.testclient import TestClient
from core.store import Store
from api.app import create_app

TOKEN = "test-token"


@pytest.fixture
def client(database):
    store = Store(database)
    a = store.upsert_account("me@example.org")
    store.upsert_message(a, "g1", thread_id="t1", subject="Bonjour",
                         body_html="<b>hi</b><script>x</script>",
                         internal_date=100, label_ids='["INBOX"]', is_unread=1)
    app = create_app(store, TOKEN, sync_fn=lambda account_id: 7)
    return TestClient(app), a


def _auth():
    return {"Authorization": f"Bearer {TOKEN}"}


def test_health_no_auth(client):
    c, _ = client
    assert c.get("/health").status_code == 200


def test_requires_token(client):
    c, _ = client
    assert c.get("/accounts").status_code == 401
    assert c.get("/accounts", headers=_auth()).status_code == 200


def test_rejects_bad_host(client):
    c, _ = client
    r = c.get("/accounts", headers={**_auth(), "Host": "evil.example"})
    assert r.status_code == 403


def test_list_messages(client):
    c, _ = client
    r = c.get("/messages", headers=_auth())
    assert r.status_code == 200
    assert r.json()[0]["subject"] == "Bonjour"


def test_message_html_sanitized(client):
    c, a = client
    mid = c.get("/messages", headers=_auth()).json()[0]["id"]
    r = c.get(f"/messages/{mid}/html", headers=_auth())
    assert "<script" not in r.text


def test_sync_endpoint(client):
    c, a = client
    r = c.post(f"/accounts/{a}/sync", headers=_auth())
    assert r.status_code == 200 and r.json()["changed"] == 7


def test_send_endpoint(database):
    store = Store(database)
    store.upsert_account("me@example.org")
    captured = {}

    def send_fn(payload):
        captured.update(payload)
        return {"gmail_id": "gX", "outbox_id": 1}

    app = create_app(store, TOKEN, send_fn=send_fn)
    c = TestClient(app)
    r = c.post("/send", headers=_auth(),
               json={"account_id": 1, "to": "d@x.co", "subject": "Hi", "body_text": "yo"})
    assert r.status_code == 200 and r.json()["gmail_id"] == "gX"
    assert captured["to"] == "d@x.co"
    assert c.post("/send", json={"account_id": 1, "to": "d@x.co"}).status_code == 401


def test_action_endpoints(database):
    store = Store(database)
    a = store.upsert_account("me@example.org")
    store.upsert_message(a, "g1", subject="x", label_ids='["INBOX"]')
    calls = []

    def act_fn(mid, action, add=None, remove=None):
        calls.append((mid, action, add, remove))
        return {"ok": True}

    app = create_app(store, TOKEN, act_fn=act_fn)
    c = TestClient(app)
    r = c.post("/messages/5/modify", headers=_auth(), json={"remove_labels": ["UNREAD"]})
    assert r.status_code == 200 and r.json()["ok"]
    assert calls[0][:2] == (5, "modify")
    assert c.post("/messages/5/trash", headers=_auth()).status_code == 200
    assert calls[1][1] == "trash"
    assert c.post("/messages/5/trash").status_code == 401


def test_glass_clamps_and_calls_glass_fn(database):
    calls = []
    app = create_app(Store(database), TOKEN, glass_fn=lambda a: calls.append(a))
    c = TestClient(app)
    assert c.post("/glass", headers=_auth(), json={"alpha": 0.3}).json()["alpha"] == 0.3
    assert c.post("/glass", headers=_auth(), json={"alpha": 5}).json()["alpha"] == 1.0
    assert c.post("/glass", headers=_auth(), json={"alpha": -2}).json()["alpha"] == 0.0
    assert calls == [0.3, 1.0, 0.0]


def test_glass_requires_auth(database):
    c = TestClient(create_app(Store(database), TOKEN))
    assert c.post("/glass", json={"alpha": 0.5}).status_code == 401


def test_glass_invalid_alpha_is_400(database):
    c = TestClient(create_app(Store(database), TOKEN))
    assert c.post("/glass", headers=_auth(), json={"alpha": "abc"}).status_code == 400
