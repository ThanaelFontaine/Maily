import base64
import pytest
from fastapi.testclient import TestClient
from core.store import Store
from api.app import create_app

TOKEN = "tok"


def _auth():
    return {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture
def store(database):
    return Store(database)


def _seed_categories(store):
    a = store.upsert_account("me@example.com")
    store.upsert_message(a, "g1", subject="Primary", internal_date=100, label_ids='["INBOX","CATEGORY_PERSONAL"]')
    store.upsert_message(a, "g2", subject="Promo", internal_date=90, label_ids='["INBOX","CATEGORY_PROMOTIONS"]')
    store.upsert_message(a, "g3", subject="Archived", internal_date=80, label_ids='["IMPORTANT"]')
    store.upsert_message(a, "g4", subject="Trashed", internal_date=70, label_ids='["INBOX"]', is_trashed=1)
    return a


def test_search_special_chars_no_500(store):
    a = store.upsert_account("me@example.com")
    store.upsert_message(a, "g1", subject="Hello", body_text="hello world", label_ids='["INBOX"]')
    c = TestClient(create_app(store, TOKEN))
    for q in ["user@domain", '"unterminated', "a:b", "foo AND", "*", ""]:
        assert c.get("/search", params={"q": q}, headers=_auth()).status_code == 200
    assert c.get("/search", params={"q": "hello"}, headers=_auth()).json()


def test_message_filters(store):
    _seed_categories(store)
    c = TestClient(create_app(store, TOKEN))

    def subs(params):
        return {m["subject"] for m in c.get("/messages" + params, headers=_auth()).json()}

    assert subs("") == {"Primary", "Promo"}
    assert subs("?category=primary") == {"Primary"}
    assert subs("?category=promotions") == {"Promo"}
    assert subs("?archived=true") == {"Archived"}
    assert subs("?trashed=true") == {"Trashed"}
    assert subs("?label=IMPORTANT") == {"Archived"}


def test_labels_lazy_refresh(store):
    a = store.upsert_account("me@example.com")
    calls = {"n": 0}

    def labels_fn(aid):
        calls["n"] += 1
        store.replace_labels(aid, [{"id": "L1", "name": "Personal", "type": "user"}])

    c = TestClient(create_app(store, TOKEN, labels_fn=labels_fn))
    r = c.get(f"/accounts/{a}/labels", headers=_auth())
    assert r.status_code == 200 and any(l["name"] == "Personal" for l in r.json()) and calls["n"] == 1
    c.get(f"/accounts/{a}/labels", headers=_auth())  # deja en cache
    assert calls["n"] == 1


def test_labels_refresh_error_swallowed(store):
    a = store.upsert_account("me@example.com")

    def labels_fn(aid):
        raise RuntimeError("boom")

    c = TestClient(create_app(store, TOKEN, labels_fn=labels_fn))
    r = c.get(f"/accounts/{a}/labels", headers=_auth())
    assert r.status_code == 200 and r.json() == []


def test_download_headers_rfc6266(store):
    a = store.upsert_account("me@example.com")
    mid = store.upsert_message(a, "g1")
    store.replace_attachments(mid, [{"filename": "x", "mime_type": "application/pdf", "size": 1,
                                     "gmail_attachment_id": "att1", "content_id": None}])
    att_id = store.list_attachments(mid)[0]["id"]
    c = TestClient(create_app(store, TOKEN, download_fn=lambda m, aid: (b"DATA", "application/pdf", "contrat\r\n契約.pdf")))
    r = c.get(f"/messages/{mid}/attachments/{att_id}/download", headers=_auth())
    cd = r.headers["content-disposition"]
    assert "\r" not in cd and "\n" not in cd and "filename*=UTF-8''" in cd and r.content == b"DATA"
    c2 = TestClient(create_app(store, TOKEN))  # no download_fn
    assert c2.get(f"/messages/{mid}/attachments/{att_id}/download", headers=_auth()).status_code == 501


def test_cid_prefix_no_collision(store):
    a = store.upsert_account("me@example.com")
    mid = store.upsert_message(a, "g1", body_html='<img src="cid:img"><img src="cid:img2">')
    store.replace_attachments(mid, [
        {"filename": "1", "mime_type": "image/png", "size": 1, "gmail_attachment_id": "a1", "content_id": "img"},
        {"filename": "2", "mime_type": "image/png", "size": 1, "gmail_attachment_id": "a2", "content_id": "img2"},
    ])
    ids = {l["content_id"]: l["id"] for l in store.list_attachments(mid)}
    c = TestClient(create_app(store, TOKEN, inline_fn=lambda m, aid: "data:AAA" if aid == ids["img"] else "data:BBB"))
    html = c.get(f"/messages/{mid}/html", headers=_auth()).text
    assert "data:BBB" in html and "data:AAA2" not in html


def test_index_host_check(store, tmp_path):
    fd = tmp_path / "f"
    fd.mkdir()
    (fd / "index.html").write_text("<html><head></head><body>x</body></html>", encoding="utf-8")
    c = TestClient(create_app(store, TOKEN, frontend_dir=fd))
    assert c.get("/").status_code == 200
    assert c.get("/", headers={"Host": "evil.example"}).status_code == 403


def test_send_attachments_passthrough(store):
    store.upsert_account("me@example.com")
    cap = {}

    def send_fn(p):
        cap.update(p)
        return {"gmail_id": "g"}

    c = TestClient(create_app(store, TOKEN, send_fn=send_fn))
    r = c.post("/send", headers=_auth(), json={
        "account_id": 1, "to": "d@example.com",
        "attachments": [{"filename": "a.txt", "mime_type": "text/plain", "data": base64.b64encode(b"hi").decode()}],
        "idempotency_key": "k1",
    })
    assert r.status_code == 200
    assert cap["attachments"][0]["filename"] == "a.txt" and cap["idempotency_key"] == "k1"
