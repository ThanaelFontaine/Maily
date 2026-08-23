import pytest
from core import accounts_service as svc
from core import auth
from core.db import Database
from core.store import Store


def test_build_gmail_client(monkeypatch):
    monkeypatch.setattr(svc, "load_credentials", lambda e: "CREDS")
    captured = {}

    def fake_build(*a, **k):
        captured["svc"] = (a, k)
        return "SERVICE"

    monkeypatch.setattr(svc, "build", fake_build)
    client = svc.build_gmail_client("me@example.org")
    assert client.service == "SERVICE"
    assert captured["svc"][0] == ("gmail", "v1")
    assert captured["svc"][1]["credentials"] == "CREDS"


def test_sync_account_calls_incremental(monkeypatch):
    calls = {}

    class FakeSyncer:
        def __init__(self, store, client, account_id):
            calls["init"] = (store, client, account_id)

        def incremental(self):
            calls["mode"] = "inc"
            return 3

        def backfill(self, query=None):
            calls["mode"] = "full"
            return 5

    monkeypatch.setattr(svc, "build_gmail_client", lambda e: "CLIENT")
    monkeypatch.setattr(svc, "Syncer", FakeSyncer)
    n = svc.sync_account("STORE", "me@example.org", 1)
    assert n == 3 and calls["mode"] == "inc"
    n2 = svc.sync_account("STORE", "me@example.org", 1, full=True)
    assert n2 == 5 and calls["mode"] == "full"


def test_add_google_account_creates_account(monkeypatch, tmp_path):
    db = Database(tmp_path / "app.sqlite")
    store = Store(db)
    monkeypatch.setattr(auth, "run_local_auth",
                        lambda open_browser=True, timeout_seconds=None: "new@example.org")
    out = svc.add_google_account(store, timeout_seconds=120)
    assert out["email"] == "new@example.org"
    assert out["account_id"] == store.list_accounts()[0]["id"]
    db.close()


def test_add_google_account_forwards_timeout(monkeypatch, tmp_path):
    db = Database(tmp_path / "app.sqlite")
    store = Store(db)
    seen = {}

    def fake_auth(open_browser=True, timeout_seconds=None):
        seen["timeout"] = timeout_seconds
        seen["browser"] = open_browser
        return "x@example.org"

    monkeypatch.setattr(auth, "run_local_auth", fake_auth)
    svc.add_google_account(store, timeout_seconds=77)
    assert seen == {"timeout": 77, "browser": True}
    db.close()


def test_add_google_account_propagates_reauth(monkeypatch, tmp_path):
    db = Database(tmp_path / "app.sqlite")
    store = Store(db)

    def boom(open_browser=True, timeout_seconds=None):
        raise auth.ReauthRequired("client absent")

    monkeypatch.setattr(auth, "run_local_auth", boom)
    with pytest.raises(auth.ReauthRequired):
        svc.add_google_account(store)
    db.close()


def test_add_google_account_rejects_concurrent(monkeypatch, tmp_path):
    db = Database(tmp_path / "app.sqlite")
    store = Store(db)
    monkeypatch.setattr(auth, "run_local_auth",
                        lambda open_browser=True, timeout_seconds=None: "y@example.org")
    assert svc._add_account_lock.acquire(blocking=False)  # simule un flow deja en cours
    try:
        with pytest.raises(svc.AddAccountInProgress):
            svc.add_google_account(store)
    finally:
        svc._add_account_lock.release()
    db.close()


def test_add_google_account_releases_lock_after_error(monkeypatch, tmp_path):
    db = Database(tmp_path / "app.sqlite")
    store = Store(db)

    def boom(open_browser=True, timeout_seconds=None):
        raise auth.ReauthRequired("nope")

    monkeypatch.setattr(auth, "run_local_auth", boom)
    with pytest.raises(auth.ReauthRequired):
        svc.add_google_account(store)
    # le verrou doit etre libere meme apres erreur
    assert svc._add_account_lock.acquire(blocking=False)
    svc._add_account_lock.release()
    db.close()
