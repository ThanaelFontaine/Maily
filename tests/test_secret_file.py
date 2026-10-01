import json
import multiprocessing
import os
import stat
import threading
import pytest
from cryptography.fernet import Fernet
from core import secret_file
from core.secret_file import SecretStoreError


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
        assert stat.S_IMODE((tmp_store / "secrets.lock").stat().st_mode) == 0o600


def test_permissions_stay_owner_only_after_rewrite(tmp_store):
    secret_file.set("a", "1")
    if os.name == "posix":
        os.chmod(tmp_store / "secrets.enc", 0o644)   # permissions relachees par un tiers
    secret_file.set("b", "2")                        # la reecriture repart d'un fichier neuf 0600
    if os.name == "posix":
        assert stat.S_IMODE((tmp_store / "secrets.enc").stat().st_mode) == 0o600


def test_write_leaves_no_temporary_file(tmp_store):
    for i in range(5):
        secret_file.set(f"k{i}", "v")
    names = sorted(p.name for p in tmp_store.iterdir())
    assert names == ["secrets.enc", "secrets.key", "secrets.lock"]


def test_existing_key_is_never_overwritten(tmp_store):
    key = Fernet.generate_key()
    (tmp_store / "secrets.key").write_bytes(key)
    secret_file.set("k", "v")
    assert (tmp_store / "secrets.key").read_bytes() == key
    assert json.loads(Fernet(key).decrypt((tmp_store / "secrets.enc").read_bytes())) == {"k": "v"}


def test_key_creation_uses_exclusive_create(tmp_store, monkeypatch):
    calls = []
    real_open = os.open

    def spy(path, flags, *a):
        if str(path).endswith("secrets.key"):
            calls.append(flags)
        return real_open(path, flags, *a)

    monkeypatch.setattr(secret_file.os, "open", spy)
    secret_file.set("k", "v")
    assert calls and all(f & os.O_EXCL and f & os.O_CREAT for f in calls)


def test_undecryptable_file_raises_and_is_left_intact(tmp_store):
    secret_file.set("account:me@example.com", "jeton-precieux")
    # Une autre cle (cle remplacee, restauration partielle...) : illisible.
    (tmp_store / "secrets.key").write_bytes(Fernet.generate_key())
    before = (tmp_store / "secrets.enc").read_bytes()
    with pytest.raises(SecretStoreError):
        secret_file.get("account:me@example.com")
    with pytest.raises(SecretStoreError):
        secret_file.set("api_token", "nouveau")      # ne doit PAS ecraser le fichier
    with pytest.raises(SecretStoreError):
        secret_file.delete("account:me@example.com")
    assert (tmp_store / "secrets.enc").read_bytes() == before


def test_corrupted_file_raises(tmp_store):
    secret_file.set("k", "v")
    (tmp_store / "secrets.enc").write_bytes(b"pas du fernet")
    with pytest.raises(SecretStoreError):
        secret_file.get("k")


def test_missing_key_with_existing_data_raises_without_creating_a_key(tmp_store):
    secret_file.set("k", "v")
    (tmp_store / "secrets.key").unlink()
    with pytest.raises(SecretStoreError):
        secret_file.set("k2", "v2")
    assert not (tmp_store / "secrets.key").exists()


def test_invalid_key_file_raises(tmp_store):
    (tmp_store / "secrets.key").write_bytes(b"trop-court")
    with pytest.raises(SecretStoreError):
        secret_file.set("k", "v")


def test_failed_replace_keeps_previous_file(tmp_store, monkeypatch):
    secret_file.set("k", "v1")
    before = (tmp_store / "secrets.enc").read_bytes()

    def boom(*a, **kw):
        raise OSError("disque plein")

    monkeypatch.setattr(secret_file.os, "replace", boom)
    with pytest.raises(OSError):
        secret_file.set("k", "v2")
    monkeypatch.undo()
    assert (tmp_store / "secrets.enc").read_bytes() == before
    assert not [p for p in tmp_store.iterdir() if p.name.endswith(".tmp")]


def test_concurrent_threads_lose_no_update():
    def worker(n):
        for i in range(15):
            secret_file.set(f"t{n}-{i}", "x")

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    for n in range(4):
        for i in range(15):
            assert secret_file.get(f"t{n}-{i}") == "x"


def _process_worker(data_dir, n, count):
    os.environ["MAILY_DATA_DIR"] = data_dir
    from core import secret_file as sf
    for i in range(count):
        sf.set(f"p{n}-{i}", str(i))


@pytest.mark.skipif(os.name != "posix", reason="verrou fcntl teste sur POSIX")
def test_concurrent_processes_lose_no_update(tmp_path, monkeypatch):
    # Plusieurs processus (app, serveur MCP, scripts) ecrivent en meme temps :
    # sans verrou inter-processus, des mises a jour disparaitraient.
    data_dir = tmp_path / "shared"
    data_dir.mkdir()
    ctx = multiprocessing.get_context("spawn")
    procs = [ctx.Process(target=_process_worker, args=(str(data_dir), n, 20)) for n in range(4)]
    for p in procs:
        p.start()
    for p in procs:
        p.join(60)
        assert p.exitcode == 0
    monkeypatch.setattr(secret_file.paths, "runtime_dir", lambda override=None: data_dir)
    for n in range(4):
        for i in range(20):
            assert secret_file.get(f"p{n}-{i}") == str(i)


def test_migrate_from_keyring(monkeypatch):
    fake = {("Maily", "api_token"): "tok", ("Maily", "account:me@example.com"): json.dumps({"refresh_token": "1//r"})}

    class FakeKeyring:
        @staticmethod
        def get_password(service, name):
            return fake.get((service, name))

    monkeypatch.setitem(__import__("sys").modules, "keyring", FakeKeyring)
    n = secret_file.migrate_from_keyring(["api_token", "account:me@example.com", "absent"])
    assert n == 2
    assert secret_file.get("api_token") == "tok"
    # N'ecrase pas une valeur deja presente.
    secret_file.set("api_token", "kept")
    assert secret_file.migrate_from_keyring(["api_token"]) == 0
    assert secret_file.get("api_token") == "kept"


def test_migrate_from_keyring_refuses_unreadable_store(tmp_store, monkeypatch):
    secret_file.set("k", "v")
    (tmp_store / "secrets.key").write_bytes(Fernet.generate_key())

    class FakeKeyring:
        @staticmethod
        def get_password(service, name):
            return "tok"

    monkeypatch.setitem(__import__("sys").modules, "keyring", FakeKeyring)
    with pytest.raises(SecretStoreError):
        secret_file.migrate_from_keyring(["api_token"])


@pytest.mark.skipif(os.name != "posix", reason="permissions POSIX")
def test_data_dir_created_owner_only(monkeypatch, tmp_path):
    # Le serveur MCP ou un script peut creer le dossier avant l'app : 0700, pas l'umask.
    fresh = tmp_path / "neuf" / "Maily"
    monkeypatch.setattr(secret_file.paths, "runtime_dir", lambda override=None: fresh)
    secret_file.set("k", "v")
    assert stat.S_IMODE(fresh.stat().st_mode) == 0o700
