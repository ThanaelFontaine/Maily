import asyncio
import pytest

pytest.importorskip("mcp")  # mcp is a main dependency; guard in case it is missing
from app import mcp_server as S  # noqa: E402


class FakeStore:
    def __init__(self):
        self._accounts = [
            {"id": 1, "email": "alex@example.com", "display_name": "Personal", "color": "#fb7185"},
            {"id": 2, "email": "team@example.org", "display_name": "Equipe", "color": "#4f7cff"},
        ]

    def list_accounts(self):
        return [dict(a) for a in self._accounts]


@pytest.fixture(autouse=True)
def fake_store(monkeypatch):
    monkeypatch.setattr(S, "_store", FakeStore())


def test_resolve_by_id_email_and_name():
    assert S._resolve_account(1)["email"] == "alex@example.com"
    assert S._resolve_account("alex@example.com")["id"] == 1
    assert S._resolve_account("Personal")["id"] == 1       # by profile name
    assert S._resolve_account("PERSONAL")["id"] == 1       # case-insensitive
    assert S._resolve_account("inconnu@example.com") is None


def test_html_to_text_strips_tags_and_invisibles():
    html = "<style>x{}</style><p>Hello​​</p><br>World<script>bad()</script>"
    txt = S._html_to_text(html)
    assert "Hello" in txt and "World" in txt
    assert "​" not in txt and "bad()" not in txt and "<" not in txt


def test_list_accounts_tool_shape():
    accs = S.maily_list_accounts()
    assert {a["email"] for a in accs} == {"alex@example.com", "team@example.org"}
    assert accs[0]["name"] == "Personal"


def test_all_tools_registered():
    tools = asyncio.run(S.mcp.list_tools())
    names = {t.name for t in tools}
    assert names == {
        "maily_list_accounts", "maily_list_messages", "maily_get_message",
        "maily_search", "maily_sync", "maily_send",
        "maily_export_eml", "maily_download_attachment", "maily_trash",
    }


def test_get_message_lists_real_attachments(monkeypatch, database):
    from core.store import Store
    store = Store(database)
    aid = store.upsert_account("alex@example.com")
    mid = store.upsert_message(aid, "g1", subject="Attachment", body_text="body")
    store.replace_attachments(mid, [
        {"filename": "invoice.pdf", "mime_type": "application/pdf", "size": 10, "gmail_attachment_id": "a1"},
        {"filename": "logo.png", "mime_type": "image/png", "size": 5, "gmail_attachment_id": "a2", "content_id": "logo"},
    ])
    monkeypatch.setattr(S, "_store", store)
    out = S.maily_get_message(mid)
    assert [a["filename"] for a in out["attachments"]] == ["invoice.pdf"]
    assert isinstance(out["attachments"][0]["attachment_id"], int)
