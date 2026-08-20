import json
import os
import stat
import pytest
from core import secret_file


@pytest.fixture(autouse=True)
def tmp_store(monkeypatch, tmp_path):
    monkeypatch.setattr(secret_file.paths, "runtime_dir", lambda override=None: tmp_path)
    return tmp_path


def test_roundtrip_and_delete():
    assert secret_file.get("k") is None
    secret_file.set("k", "v")
    assert secret_file.get("k") == "v"
    secret_file.delete("k")
    assert secret_file.get("k") is None


def test_data_is_encrypted_at_rest(tmp_store):
    secret_file.set("api_token", "s3cr3t-value")
    blob = (tmp_store / "secrets.enc").read_bytes()
    assert b"s3cr3t-value" not in blob  # jamais en clair sur le disque


def test_key_file_is_owner_only(tmp_store):
    secret_file.set("k", "v")
    if os.name == "posix":
        assert stat.S_IMODE((tmp_store / "secrets.key").stat().st_mode) == 0o600
        assert stat.S_IMODE((tmp_store / "secrets.enc").stat().st_mode) == 0o600


def test_migrate_from_keyring(monkeypatch):
    fake = {("Maily", "api_token"): "tok", ("Maily", "account:me@x"): json.dumps({"refresh_token": "1//r"})}

    class FakeKeyring:
        @staticmethod
        def get_password(service, name):
            return fake.get((service, name))

    monkeypatch.setitem(__import__("sys").modules, "keyring", FakeKeyring)
    n = secret_file.migrate_from_keyring(["api_token", "account:me@x", "absent"])
    assert n == 2
    assert secret_file.get("api_token") == "tok"
    # N'ecrase pas une valeur deja presente.
    secret_file.set("api_token", "kept")
    assert secret_file.migrate_from_keyring(["api_token"]) == 0
    assert secret_file.get("api_token") == "kept"
