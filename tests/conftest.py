"""Garde-fous communs a tous les tests.

Aucun test ne doit toucher le vrai dossier de donnees de l'utilisateur
(~/Library/Application Support/Maily, %APPDATA%/Maily, ~/.local/share/maily)
ni le vrai Trousseau / keyring : chaque test recoit un dossier de donnees
temporaire (MAILY_DATA_DIR) et un keyring nul.
"""
import pytest
from core import db as dbmod


@pytest.fixture(autouse=True)
def _isolate_user_data(monkeypatch, tmp_path_factory):
    data_dir = tmp_path_factory.mktemp("maily-data")
    monkeypatch.setenv("MAILY_DATA_DIR", str(data_dir))
    monkeypatch.setenv("PYTHON_KEYRING_BACKEND", "keyring.backends.null.Keyring")
    monkeypatch.setenv("MAILY_NO_BIOMETRIC", "1")
    # TestClient envoie Host: testserver ; accepte seulement pendant les tests.
    from api import app as api_app
    monkeypatch.setattr(api_app, "_LOCAL_HOSTS", api_app._LOCAL_HOSTS | {"testserver"})
    yield data_dir


@pytest.fixture
def database(tmp_path):
    d = dbmod.Database(tmp_path / "app.sqlite")
    yield d
    d.close()
