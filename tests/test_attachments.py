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


def _img_attrs(html):
    from html.parser import HTMLParser

    found = []

    class P(HTMLParser):
        def handle_starttag(self, tag, attrs):
            if tag == "img":
                found.append(dict(attrs))

    P().feed(html)
    return found


def _html_with_cid(database, body_html, content_id, allow_remote=False):
    store = Store(database)
    a = store.upsert_account("me@example.com")
    mid = store.upsert_message(a, "g1", body_html=body_html)
    store.replace_attachments(mid, [{"filename": "x.png", "mime_type": "image/png",
                                     "size": 3, "gmail_attachment_id": "att1", "content_id": content_id}])
    app = create_app(store, TOKEN, inline_fn=lambda m, aid: "data:image/png;base64,AAAA")
    return TestClient(app).get(f"/messages/{mid}/html?allow_remote={'true' if allow_remote else 'false'}",
                               headers=_auth())


def test_hostile_content_id_cannot_leave_the_src_attribute(database):
    """MAIL-35: a Content-ID with quotes and brackets used to move the quotes of the sanitized HTML."""
    body = '<img src="cid:a"><img alt="b srcset=https://evil.example/p.gif x">'
    r = _html_with_cid(database, body, 'a"><img alt=')
    assert r.status_code == 200
    # The text stays inside the alt value: no tag carries a srcset or a remote src.
    attrs = _img_attrs(r.text)
    assert attrs and all("srcset" not in a and not a.get("src", "").startswith("http") for a in attrs)
    assert "data:image/png" not in r.text
    assert r.headers["X-Maily-Blocked-Remote"] == "0"


def test_hostile_content_id_with_space_is_ignored(database):
    r = _html_with_cid(database, '<img src="cid:a b"><img src="cid:a">', "a b")
    assert "data:image/png" not in r.text


def test_ordinary_content_ids_are_still_substituted(database):
    for cid in ("logo1", "image001.png@01D6A5B2.4F3C2A10", "ii_kx3a9+z=1"):
        r = _html_with_cid(database, f'<img src="cid:{cid}"><p>hi</p>', cid)
        assert 'src="data:image/png;base64,AAAA"' in r.text and "cid:" not in r.text, cid
        assert r.headers["X-Maily-Blocked-Remote"] == "0"


def test_cid_in_the_text_is_not_rewritten(database):
    r = _html_with_cid(database, '<p>write cid:logo1 in the src</p><img src="cid:logo1">', "logo1")
    assert "write cid:logo1 in the src" in r.text and r.text.count("data:image/png") == 1
