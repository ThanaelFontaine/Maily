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


def test_sync_account_calls_incremental(monkeypatch, tmp_path):
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

    db = Database(tmp_path / "app.sqlite")
    store = Store(db)
    aid = store.upsert_account("me@example.org")   # provider gmail par défaut
    monkeypatch.setattr(svc, "build_gmail_client", lambda e: "CLIENT")
    monkeypatch.setattr(svc, "Syncer", FakeSyncer)
    n = svc.sync_account(store, "me@example.org", aid)
    assert n == 3 and calls["mode"] == "inc"
    n2 = svc.sync_account(store, "me@example.org", aid, full=True)
    assert n2 == 5 and calls["mode"] == "full"
    db.close()


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


def test_logout_account_deletes_secret_and_cache(monkeypatch, tmp_path):
    db = Database(tmp_path / "app.sqlite")
    store = Store(db)
    aid = store.upsert_account("me@example.org")
    store.upsert_message(aid, "g1", subject="x", label_ids='["INBOX"]')
    deleted = {}
    monkeypatch.setattr(svc.secrets_store, "delete_account_token",
                        lambda email: deleted.setdefault("gmail", email))
    svc.logout_account(store, aid)
    assert deleted == {"gmail": "me@example.org"}
    assert store.get_account(aid) is None
    assert store.list_messages(aid) == []
    db.close()


def test_logout_account_unknown_is_noop(monkeypatch, tmp_path):
    db = Database(tmp_path / "app.sqlite")
    store = Store(db)
    monkeypatch.setattr(svc.secrets_store, "delete_account_token", lambda email: None)
    # ne doit pas lever
    svc.logout_account(store, 9999)
    db.close()


def test_export_eml_gmail(monkeypatch, tmp_path):
    import base64
    db = Database(tmp_path / "app.sqlite")
    store = Store(db)
    aid = store.upsert_account("me@example.org")
    mid = store.upsert_message(aid, "gmABC", subject="Ma facture", label_ids='["INBOX"]')
    raw_bytes = b"From: a@b.co\r\nSubject: Ma facture\r\n\r\nCorps du mail."
    b64 = base64.urlsafe_b64encode(raw_bytes).decode().rstrip("=")  # style Gmail (sans padding)

    class FakeClient:
        def get_message(self, gmail_id, fmt="full"):
            assert gmail_id == "gmABC" and fmt == "raw"
            return {"raw": b64}

    monkeypatch.setattr(svc, "build_gmail_client", lambda e: FakeClient())
    data, filename = svc.export_eml(store, mid)
    assert data == raw_bytes
    assert filename.endswith(".eml") and "facture" in filename.lower()
    db.close()


def test_export_eml_unknown_message(tmp_path):
    db = Database(tmp_path / "app.sqlite")
    store = Store(db)
    with pytest.raises(ValueError):
        svc.export_eml(store, 12345)
    db.close()


# ------------------------- Orange / IMAP -------------------------

class _FakeImapClient:
    def __init__(self, host=None, port=None, username=None, password=None, fail=False):
        self.host, self.port, self.username, self.password = host, port, username, password
        self.fail = fail
        self.events = []

    def connect(self):
        if self.fail:
            from core.imap_client import ImapError
            raise ImapError("bad creds")
        self.events.append("connect"); return self

    def select_inbox(self): self.events.append("select"); return 1000
    def select_folder(self, name): self.events.append(("select", name)); return 1000
    def fetch(self, uid): return (b"From: a@b\r\nSubject: X\r\n\r\nhi", True)
    def move_to_trash(self, uid): self.events.append(("trash", uid))
    def logout(self): self.events.append("logout")


def test_add_imap_account_ok(monkeypatch, tmp_path):
    db = Database(tmp_path / "app.sqlite"); store = Store(db)
    saved = {}
    monkeypatch.setattr(svc, "ImapClient", lambda **kw: _FakeImapClient(**kw))
    monkeypatch.setattr(svc.secrets_store, "save_imap_credentials",
                        lambda email, creds: saved.update({email: creds}))
    out = svc.add_imap_account(store, "me@orange.fr", "secret", host="imap.orange.fr", port=993)
    assert out["email"] == "me@orange.fr"
    acc = dict(store.get_account(out["account_id"]))
    assert acc["provider"] == "imap"
    assert saved["me@orange.fr"]["password"] == "secret"
    db.close()


def test_add_imap_account_bad_credentials(monkeypatch, tmp_path):
    db = Database(tmp_path / "app.sqlite"); store = Store(db)
    from core.imap_client import ImapError
    monkeypatch.setattr(svc, "ImapClient", lambda **kw: _FakeImapClient(fail=True, **kw))
    monkeypatch.setattr(svc.secrets_store, "save_imap_credentials", lambda *a: None)
    with pytest.raises(ImapError):
        svc.add_imap_account(store, "me@orange.fr", "wrong")
    # aucun compte créé
    assert store.list_accounts() == []
    db.close()


def test_sync_account_branches_to_imap(monkeypatch, tmp_path):
    db = Database(tmp_path / "app.sqlite"); store = Store(db)
    aid = store.upsert_account("me@orange.fr", provider="imap")
    calls = {}

    class FakeSyncer:
        def __init__(self, s, c, acc_id, backfill_months=12): calls["init"] = acc_id
        def backfill(self): calls["mode"] = "full"; return 4
        def incremental(self): calls["mode"] = "inc"; return 1

    monkeypatch.setattr(svc, "build_imap_client", lambda e: "IMAPCLIENT")
    monkeypatch.setattr(svc, "ImapSyncer", FakeSyncer)
    assert svc.sync_account(store, "me@orange.fr", aid, full=True) == 4
    assert calls["mode"] == "full"
    assert svc.sync_account(store, "me@orange.fr", aid) == 1
    assert calls["mode"] == "inc"
    db.close()


def test_trash_message_imap(monkeypatch, tmp_path):
    from core.imap_client import imap_msg_key
    db = Database(tmp_path / "app.sqlite"); store = Store(db)
    aid = store.upsert_account("me@orange.fr", provider="imap")
    mid = store.upsert_message(aid, imap_msg_key("INBOX.Sent", 1000, 7),
                               subject="X", label_ids='["INBOX.Sent"]')
    fake = _FakeImapClient()
    monkeypatch.setattr(svc, "build_imap_client", lambda e: fake)
    svc.trash_message(store, "me@orange.fr", mid)
    assert ("select", "INBOX.Sent") in fake.events   # sélectionne le bon dossier
    assert ("trash", 7) in fake.events
    assert dict(store.get_message(mid))["is_trashed"] == 1
    db.close()


def test_export_eml_imap(monkeypatch, tmp_path):
    db = Database(tmp_path / "app.sqlite"); store = Store(db)
    aid = store.upsert_account("me@orange.fr", provider="imap")
    mid = store.upsert_message(aid, "1000.7", subject="Fac", label_ids='["INBOX"]')
    monkeypatch.setattr(svc, "_imap_fetch_raw", lambda email, gid: b"RAW-IMAP")
    data, filename = svc.export_eml(store, mid)
    assert data == b"RAW-IMAP" and filename.endswith(".eml")
    db.close()
