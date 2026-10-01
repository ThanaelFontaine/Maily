import pytest
from fastapi.testclient import TestClient
from core.store import Store
from api.app import create_app

TOKEN = "test-token"


@pytest.fixture
def client(database):
    store = Store(database)
    a = store.upsert_account("me@example.com")
    store.upsert_message(a, "g1", thread_id="t1", subject="Hello",
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
    assert r.json()[0]["subject"] == "Hello"


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
    store.upsert_account("me@example.com")
    captured = {}

    def send_fn(payload):
        captured.update(payload)
        return {"gmail_id": "gX", "outbox_id": 1}

    app = create_app(store, TOKEN, send_fn=send_fn)
    c = TestClient(app)
    r = c.post("/send", headers=_auth(),
               json={"account_id": 1, "to": "d@example.com", "subject": "Hi", "body_text": "yo"})
    assert r.status_code == 200 and r.json()["gmail_id"] == "gX"
    assert captured["to"] == "d@example.com"
    assert c.post("/send", json={"account_id": 1, "to": "d@example.com"}).status_code == 401


def test_action_endpoints(database):
    store = Store(database)
    a = store.upsert_account("me@example.com")
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


def test_patch_account_name_and_color(client):
    c, a = client
    r = c.patch(f"/accounts/{a}", headers=_auth(), json={"display_name": "Personal", "color": "#12ab34"})
    assert r.status_code == 200
    body = r.json()
    assert body["display_name"] == "Personal" and body["color"] == "#12ab34"
    # persistance
    accs = c.get("/accounts", headers=_auth()).json()
    me = [x for x in accs if x["id"] == a][0]
    assert me["display_name"] == "Personal" and me["color"] == "#12ab34"


def test_patch_account_partial_keeps_other(client):
    c, a = client
    c.patch(f"/accounts/{a}", headers=_auth(), json={"color": "#abcdef"})
    c.patch(f"/accounts/{a}", headers=_auth(), json={"display_name": "X"})
    me = [x for x in c.get("/accounts", headers=_auth()).json() if x["id"] == a][0]
    assert me["color"] == "#abcdef" and me["display_name"] == "X"


def test_patch_account_bad_color_is_400(client):
    c, a = client
    assert c.patch(f"/accounts/{a}", headers=_auth(), json={"color": "red"}).status_code == 400


def test_patch_account_unknown_is_404(client):
    c, _ = client
    assert c.patch("/accounts/9999", headers=_auth(), json={"display_name": "Y"}).status_code == 404


def test_patch_account_requires_auth(client):
    c, a = client
    assert c.patch(f"/accounts/{a}", json={"display_name": "Z"}).status_code == 401


def test_glass_get_returns_value(database):
    app = create_app(Store(database), TOKEN, glass_get_fn=lambda: 0.42)
    c = TestClient(app)
    r = c.get("/glass", headers=_auth())
    assert r.status_code == 200 and r.json()["alpha"] == 0.42


def test_glass_get_default_and_auth(database):
    c = TestClient(create_app(Store(database), TOKEN))
    assert c.get("/glass").status_code == 401
    assert c.get("/glass", headers=_auth()).json()["alpha"] == 0.6


def test_add_google_endpoint_nominal(database):
    app = create_app(Store(database), TOKEN,
                     add_google_fn=lambda: {"account_id": 3, "email": "z@example.com"})
    c = TestClient(app)
    r = c.post("/accounts/google", headers=_auth())
    assert r.status_code == 200 and r.json()["email"] == "z@example.com"


def test_add_google_endpoint_requires_auth(database):
    app = create_app(Store(database), TOKEN, add_google_fn=lambda: {})
    assert TestClient(app).post("/accounts/google").status_code == 401


def test_add_google_endpoint_not_wired_is_501(database):
    c = TestClient(create_app(Store(database), TOKEN))
    assert c.post("/accounts/google", headers=_auth()).status_code == 501


def test_add_google_endpoint_reauth_is_400(database):
    from core.auth import ReauthRequired

    def boom():
        raise ReauthRequired("OAuth client missing")

    c = TestClient(create_app(Store(database), TOKEN, add_google_fn=boom))
    r = c.post("/accounts/google", headers=_auth())
    assert r.status_code == 400 and "OAuth" in r.json()["detail"]


def test_add_google_endpoint_timeout_is_408(database):
    from core.auth import AuthTimeout

    def boom():
        raise AuthTimeout("timed out")

    c = TestClient(create_app(Store(database), TOKEN, add_google_fn=boom))
    assert c.post("/accounts/google", headers=_auth()).status_code == 408


def test_add_google_endpoint_in_progress_is_409(database):
    from core.accounts_service import AddAccountInProgress

    def boom():
        raise AddAccountInProgress("deja en cours")

    c = TestClient(create_app(Store(database), TOKEN, add_google_fn=boom))
    assert c.post("/accounts/google", headers=_auth()).status_code == 409


def test_delete_account_endpoint(database):
    store = Store(database)
    aid = store.upsert_account("me@example.com")
    calls = []
    app = create_app(store, TOKEN, logout_fn=lambda account_id: calls.append(account_id))
    c = TestClient(app)
    r = c.delete(f"/accounts/{aid}", headers=_auth())
    assert r.status_code == 200 and r.json()["ok"] is True
    assert calls == [aid]


def test_delete_account_requires_auth(database):
    store = Store(database)
    aid = store.upsert_account("me@example.com")
    app = create_app(store, TOKEN, logout_fn=lambda account_id: None)
    assert TestClient(app).delete(f"/accounts/{aid}").status_code == 401


def test_delete_account_not_wired_is_501(database):
    store = Store(database)
    aid = store.upsert_account("me@example.com")
    c = TestClient(create_app(store, TOKEN))
    assert c.delete(f"/accounts/{aid}", headers=_auth()).status_code == 501


def test_eml_endpoint(database):
    store = Store(database)
    aid = store.upsert_account("me@example.com")
    mid = store.upsert_message(aid, "g1", subject="X", label_ids='["INBOX"]')
    app = create_app(store, TOKEN, eml_fn=lambda message_id: (b"RAW-EML-BYTES", "x.eml"))
    c = TestClient(app)
    r = c.get(f"/messages/{mid}/eml", headers=_auth())
    assert r.status_code == 200
    assert r.content == b"RAW-EML-BYTES"
    assert "attachment" in r.headers.get("content-disposition", "")
    assert "x.eml" in r.headers.get("content-disposition", "")


def test_eml_endpoint_requires_auth(database):
    store = Store(database)
    mid = store.upsert_message(store.upsert_account("me@example.com"), "g1", subject="X")
    app = create_app(store, TOKEN, eml_fn=lambda message_id: (b"x", "x.eml"))
    assert TestClient(app).get(f"/messages/{mid}/eml").status_code == 401


def test_eml_endpoint_not_wired_is_501(database):
    store = Store(database)
    mid = store.upsert_message(store.upsert_account("me@example.com"), "g1", subject="X")
    c = TestClient(create_app(store, TOKEN))
    assert c.get(f"/messages/{mid}/eml", headers=_auth()).status_code == 501


def test_add_imap_endpoint_nominal(database):
    store = Store(database)
    captured = {}

    def add_imap_fn(email, password, host, port):
        captured.update(email=email, password=password, host=host, port=port)
        return {"account_id": 5, "email": email}

    app = create_app(store, TOKEN, add_imap_fn=add_imap_fn)
    c = TestClient(app)
    r = c.post("/accounts/imap", headers=_auth(),
               json={"email": "me@example.net", "password": "pw"})
    assert r.status_code == 200 and r.json()["email"] == "me@example.net"
    assert captured["host"] == "imap.orange.fr" and captured["port"] == 993
    assert captured["password"] == "pw"


def test_add_imap_endpoint_requires_auth(database):
    app = create_app(Store(database), TOKEN, add_imap_fn=lambda *a: {})
    assert TestClient(app).post("/accounts/imap", json={"email": "a", "password": "b"}).status_code == 401


def test_add_imap_endpoint_bad_credentials_is_400(database):
    from core.imap_client import ImapError

    def boom(email, password, host, port):
        raise ImapError("bad creds")

    c = TestClient(create_app(Store(database), TOKEN, add_imap_fn=boom))
    r = c.post("/accounts/imap", headers=_auth(), json={"email": "a@example.net", "password": "x"})
    assert r.status_code == 400


def test_add_imap_endpoint_not_wired_is_501(database):
    c = TestClient(create_app(Store(database), TOKEN))
    assert c.post("/accounts/imap", headers=_auth(),
                  json={"email": "a@example.net", "password": "x"}).status_code == 501


def test_message_html_reports_blocked_remote(database):
    store = Store(database)
    a = store.upsert_account("me@example.com")
    mid = store.upsert_message(a, "g9", subject="Pixel",
                               body_html='<p>x</p><img src="https://tracker.example/p.gif">',
                               internal_date=1, label_ids='["INBOX"]')
    c = TestClient(create_app(store, TOKEN))
    r = c.get(f"/messages/{mid}/html", headers=_auth())
    assert r.headers["x-maily-blocked-remote"] == "1"
    assert "tracker.example" not in r.text
    r2 = c.get(f"/messages/{mid}/html?allow_remote=true", headers=_auth())
    assert r2.headers["x-maily-blocked-remote"] == "0"
    assert "tracker.example" in r2.text


def test_about_endpoint(client, monkeypatch, tmp_path):
    import core
    c, _ = client
    monkeypatch.setenv("MAILY_DATA_DIR", str(tmp_path / "d"))
    assert c.get("/about").status_code == 401
    r = c.get("/about", headers=_auth())
    assert r.status_code == 200
    assert r.json() == {"version": core.__version__, "data_dir": str(tmp_path / "d")}
