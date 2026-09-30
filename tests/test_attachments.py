import base64
import pytest
from fastapi.testclient import TestClient
from core.store import Store
from core import accounts_service as svc
from api.app import create_app

TOKEN = "tok"


@pytest.fixture
def store(database):
    return Store(database)


def _auth():
    return {"Authorization": f"Bearer {TOKEN}"}


def test_replace_and_list_attachments(store):
    acc = store.upsert_account("me@example.com")
    mid = store.upsert_message(acc, "g1")
    att = {"filename": "cv.pdf", "mime_type": "application/pdf", "size": 10,
           "gmail_attachment_id": "att1", "content_id": None}
    store.replace_attachments(mid, [att])
    assert len(store.list_attachments(mid)) == 1
    store.replace_attachments(mid, [att])  # idempotent
    assert len(store.list_attachments(mid)) == 1


def test_fetch_attachment_caches(store, tmp_path, monkeypatch):
    acc = store.upsert_account("me@example.com")
    mid = store.upsert_message(acc, "gX")
    store.replace_attachments(mid, [{"filename": "c v.pdf", "mime_type": "application/pdf",
                                     "size": 3, "gmail_attachment_id": "att1", "content_id": None}])
    att_id = store.list_attachments(mid)[0]["id"]

    calls = {"n": 0}

    class FakeClient:
        def get_attachment(self, gid, aid):
            calls["n"] += 1
            return {"data": base64.urlsafe_b64encode(b"PDF").decode()}

    monkeypatch.setattr(svc, "build_gmail_client", lambda e: FakeClient())

    data, mime, fn = svc.fetch_attachment(store, "me@example.com", mid, att_id, str(tmp_path))
    assert data == b"PDF" and mime == "application/pdf"
    data2, _, _ = svc.fetch_attachment(store, "me@example.com", mid, att_id, str(tmp_path))
    assert data2 == b"PDF" and calls["n"] == 1  # 2e appel = cache
    basename = store.get_attachment(att_id)["local_path"].split("/")[-1]
    assert " " not in basename and "c_v.pdf" in basename


def test_attachments_endpoints(database):
    store = Store(database)
    a = store.upsert_account("me@example.com")
    mid = store.upsert_message(a, "g1", body_html='<img src="cid:logo1"><p>hi</p>')
    store.replace_attachments(mid, [{"filename": "logo.png", "mime_type": "image/png",
                                     "size": 3, "gmail_attachment_id": "att1", "content_id": "logo1"}])
    att_id = store.list_attachments(mid)[0]["id"]

    app = create_app(store, TOKEN,
                     download_fn=lambda m, aid: (b"PNG", "image/png", "logo.png"),
                     inline_fn=lambda m, aid: "data:image/png;base64,UE5H")
    c = TestClient(app)

    r = c.get(f"/messages/{mid}/attachments", headers=_auth())
    assert r.status_code == 200 and r.json()[0]["filename"] == "logo.png"

    r = c.get(f"/messages/{mid}/attachments/{att_id}/download", headers=_auth())
    assert r.status_code == 200 and r.content == b"PNG"
    assert "attachment" in r.headers["content-disposition"]

    r = c.get(f"/messages/{mid}/html", headers=_auth())
    assert "data:image/png;base64,UE5H" in r.text and "cid:logo1" not in r.text
