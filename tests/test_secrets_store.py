import pytest
from core import secrets_store


@pytest.fixture(autouse=True)
def fake_keyring(monkeypatch):
    store = {}
    monkeypatch.setattr(secrets_store.keyring, "set_password",
                        lambda s, k, v: store.__setitem__((s, k), v))
    monkeypatch.setattr(secrets_store.keyring, "get_password",
                        lambda s, k: store.get((s, k)))
    monkeypatch.setattr(secrets_store.keyring, "delete_password",
                        lambda s, k: store.pop((s, k), None))
    return store


def test_client_config_roundtrip():
    assert secrets_store.load_client_config() is None
    secrets_store.save_client_config("cid.apps.googleusercontent.com", "GOCSPX-secret")
    cfg = secrets_store.load_client_config()
    assert cfg["client_id"] == "cid.apps.googleusercontent.com"
    assert cfg["client_secret"] == "GOCSPX-secret"


def test_account_token_roundtrip():
    secrets_store.save_account_token("me@example.org", {"refresh_token": "1//abc"})
    assert secrets_store.load_account_token("me@example.org")["refresh_token"] == "1//abc"
    secrets_store.delete_account_token("me@example.org")
    assert secrets_store.load_account_token("me@example.org") is None
