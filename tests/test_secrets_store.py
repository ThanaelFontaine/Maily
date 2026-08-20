import pytest
from core import secrets_store


@pytest.fixture(autouse=True)
def tmp_secret_store(monkeypatch, tmp_path):
    from core import secret_file
    monkeypatch.setattr(secret_file.paths, "runtime_dir", lambda override=None: tmp_path)
    return tmp_path


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
