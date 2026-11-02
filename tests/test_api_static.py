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


@pytest.mark.parametrize("url", ["/", "/?k=" + TOKEN, "/?launch=x"])
def test_index_never_serves_the_token(client, url):
    r = client.get(url)
    assert r.status_code == 200
    assert "Maily" in r.text
    assert "MAILY_TOKEN" not in r.text
    assert TOKEN not in r.text


def test_index_refuses_foreign_host(client):
    assert client.get("/", headers={"host": "evil.example"}).status_code == 403


def test_static_served(client):
    r = client.get("/static/app.js")
    assert r.status_code == 200
    assert "console.log" in r.text


def test_get_account(database):
    store = Store(database)
    a = store.upsert_account("me@example.com", display_name="Me")
    assert store.get_account(a)["email"] == "me@example.com"
    assert store.get_account(9999) is None
