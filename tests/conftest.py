"""Safeguards shared by every test.

No test may touch the user's real data folder (~/Library/Application
Support/Maily, %APPDATA%/Maily, ~/.local/share/maily) or the real Keychain /
keyring: each test gets a temporary data folder (MAILY_DATA_DIR) and a null
keyring.
"""
import pytest
from core import db as dbmod


@pytest.fixture(autouse=True)
def _isolate_user_data(monkeypatch, tmp_path_factory):
    data_dir = tmp_path_factory.mktemp("maily-data")
    monkeypatch.setenv("MAILY_DATA_DIR", str(data_dir))
    monkeypatch.setenv("PYTHON_KEYRING_BACKEND", "keyring.backends.null.Keyring")
    monkeypatch.setenv("MAILY_NO_BIOMETRIC", "1")
    # TestClient sends Host: testserver; accepted during the tests only.
    from api import app as api_app
    monkeypatch.setattr(api_app, "_LOCAL_HOSTS", api_app._LOCAL_HOSTS | {"testserver"})
    yield data_dir


@pytest.fixture
def database(tmp_path):
    d = dbmod.Database(tmp_path / "app.sqlite")
    yield d
    d.close()
