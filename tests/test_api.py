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
