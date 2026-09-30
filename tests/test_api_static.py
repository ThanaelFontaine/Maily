import pytest
from fastapi.testclient import TestClient
from core.store import Store
from api.app import create_app

TOKEN = "tok"


@pytest.fixture
def client(database, tmp_path):
    store = Store(database)
    fd = tmp_path / "frontend"
    fd.mkdir()
    (fd / "index.html").write_text("<html><head></head><body>Maily</body></html>", encoding="utf-8")
    (fd / "app.js").write_text("console.log('hi');", encoding="utf-8")
    app = create_app(store, TOKEN, frontend_dir=fd)
    return TestClient(app)


def test_index_injects_token(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "window.MAILY_TOKEN" in r.text
    assert TOKEN in r.text


def test_static_served(client):
    r = client.get("/static/app.js")
    assert r.status_code == 200
    assert "console.log" in r.text


def test_get_account(database):
    store = Store(database)
    a = store.upsert_account("me@example.com", display_name="Moi")
    assert store.get_account(a)["email"] == "me@example.com"
    assert store.get_account(9999) is None
