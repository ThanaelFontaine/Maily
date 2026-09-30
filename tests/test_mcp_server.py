import asyncio
import pytest

pytest.importorskip("mcp")  # mcp est une dependance principale ; garde-fou si absent
from app import mcp_server as S  # noqa: E402


class FakeStore:
    def __init__(self):
        self._accounts = [
            {"id": 1, "email": "alex@example.com", "display_name": "Perso", "color": "#fb7185"},
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
    assert S._resolve_account("Perso")["id"] == 1          # par nom de profil
    assert S._resolve_account("PERSO")["id"] == 1          # insensible a la casse
    assert S._resolve_account("inconnu@example.com") is None


def test_html_to_text_strips_tags_and_invisibles():
    html = "<style>x{}</style><p>Bonjour​​</p><br>Monde<script>bad()</script>"
    txt = S._html_to_text(html)
    assert "Bonjour" in txt and "Monde" in txt
    assert "​" not in txt and "bad()" not in txt and "<" not in txt


def test_list_accounts_tool_shape():
    accs = S.maily_list_accounts()
    assert {a["email"] for a in accs} == {"alex@example.com", "team@example.org"}
    assert accs[0]["name"] == "Perso"


def test_all_tools_registered():
    tools = asyncio.run(S.mcp.list_tools())
    names = {t.name for t in tools}
    assert names == {
        "maily_list_accounts", "maily_list_messages", "maily_get_message",
        "maily_search", "maily_sync", "maily_send",
        "maily_export_eml", "maily_download_attachment", "maily_trash",
    }
