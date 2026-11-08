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
    client = svc.build_gmail_client("me@example.com")
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
    aid = store.upsert_account("me@example.com")   # gmail provider by default
    monkeypatch.setattr(svc, "build_gmail_client", lambda e: "CLIENT")
    monkeypatch.setattr(svc, "Syncer", FakeSyncer)
    n = svc.sync_account(store, "me@example.com", aid)
    assert n == 3 and calls["mode"] == "inc"
    n2 = svc.sync_account(store, "me@example.com", aid, full=True)
    assert n2 == 5 and calls["mode"] == "full"
    db.close()


def test_add_google_account_creates_account(monkeypatch, tmp_path):
    db = Database(tmp_path / "app.sqlite")
    store = Store(db)
    monkeypatch.setattr(auth, "run_local_auth",
                        lambda open_browser=True, timeout_seconds=None: "new@example.com")
    out = svc.add_google_account(store, timeout_seconds=120)
    assert out["email"] == "new@example.com"
    assert out["account_id"] == store.list_accounts()[0]["id"]
    db.close()


def test_add_google_account_forwards_timeout(monkeypatch, tmp_path):
    db = Database(tmp_path / "app.sqlite")
    store = Store(db)
    seen = {}

    def fake_auth(open_browser=True, timeout_seconds=None):
        seen["timeout"] = timeout_seconds
        seen["browser"] = open_browser
        return "x@example.com"

    monkeypatch.setattr(auth, "run_local_auth", fake_auth)
    svc.add_google_account(store, timeout_seconds=77)
    assert seen == {"timeout": 77, "browser": True}
    db.close()


def test_add_google_account_propagates_reauth(monkeypatch, tmp_path):
    db = Database(tmp_path / "app.sqlite")
    store = Store(db)

    def boom(open_browser=True, timeout_seconds=None):
        raise auth.ReauthRequired("client missing")

    monkeypatch.setattr(auth, "run_local_auth", boom)
    with pytest.raises(auth.ReauthRequired):
        svc.add_google_account(store)
    db.close()


def test_add_google_account_rejects_concurrent(monkeypatch, tmp_path):
    db = Database(tmp_path / "app.sqlite")
    store = Store(db)
    monkeypatch.setattr(auth, "run_local_auth",
                        lambda open_browser=True, timeout_seconds=None: "y@example.com")
    assert svc._add_account_lock.acquire(blocking=False)  # simulates a flow already in progress
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
    # the lock must be released even after an error
    assert svc._add_account_lock.acquire(blocking=False)
    svc._add_account_lock.release()
    db.close()


def test_logout_account_deletes_secret_and_cache(monkeypatch, tmp_path):
    db = Database(tmp_path / "app.sqlite")
    store = Store(db)
    aid = store.upsert_account("me@example.com")
    store.upsert_message(aid, "g1", subject="x", label_ids='["INBOX"]')
    deleted = {}
    monkeypatch.setattr(svc.secrets_store, "delete_account_token",
                        lambda email: deleted.setdefault("gmail", email))
    svc.logout_account(store, aid)
    assert deleted == {"gmail": "me@example.com"}
    assert store.get_account(aid) is None
    assert store.list_messages(aid) == []
    db.close()


def test_logout_account_unknown_is_noop(monkeypatch, tmp_path):
    db = Database(tmp_path / "app.sqlite")
    store = Store(db)
    monkeypatch.setattr(svc.secrets_store, "delete_account_token", lambda email: None)
    # must not raise
    svc.logout_account(store, 9999)
    db.close()


def test_export_eml_gmail(monkeypatch, tmp_path):
    import base64
    db = Database(tmp_path / "app.sqlite")
    store = Store(db)
    aid = store.upsert_account("me@example.com")
    mid = store.upsert_message(aid, "gmABC", subject="My invoice", label_ids='["INBOX"]')
    raw_bytes = b"From: a@example.com\r\nSubject: My invoice\r\n\r\nMail body."
    b64 = base64.urlsafe_b64encode(raw_bytes).decode().rstrip("=")  # style Gmail (sans padding)

    class FakeClient:
        def get_message(self, gmail_id, fmt="full"):
            assert gmail_id == "gmABC" and fmt == "raw"
            return {"raw": b64}

    monkeypatch.setattr(svc, "build_gmail_client", lambda e: FakeClient())
    data, filename = svc.export_eml(store, mid)
    assert data == raw_bytes
    assert filename.endswith(".eml") and "invoice" in filename.lower()
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
    out = svc.add_imap_account(store, "me@example.net", "secret", host="imap.orange.fr", port=993)
    assert out["email"] == "me@example.net"
    acc = dict(store.get_account(out["account_id"]))
    assert acc["provider"] == "imap"
    assert saved["me@example.net"]["password"] == "secret"
    db.close()


def test_add_imap_account_bad_credentials(monkeypatch, tmp_path):
    db = Database(tmp_path / "app.sqlite"); store = Store(db)
    from core.imap_client import ImapError
    monkeypatch.setattr(svc, "ImapClient", lambda **kw: _FakeImapClient(fail=True, **kw))
    monkeypatch.setattr(svc.secrets_store, "save_imap_credentials", lambda *a: None)
    with pytest.raises(ImapError):
        svc.add_imap_account(store, "me@example.net", "wrong")
    # no account created
    assert store.list_accounts() == []
    db.close()


def test_sync_account_branches_to_imap(monkeypatch, tmp_path):
    db = Database(tmp_path / "app.sqlite"); store = Store(db)
    aid = store.upsert_account("me@example.net", provider="imap")
    calls = {}

    class FakeSyncer:
        def __init__(self, s, c, acc_id, backfill_months=12): calls["init"] = acc_id
        def backfill(self): calls["mode"] = "full"; return 4
        def incremental(self): calls["mode"] = "inc"; return 1

    monkeypatch.setattr(svc, "build_imap_client", lambda e: "IMAPCLIENT")
    monkeypatch.setattr(svc, "ImapSyncer", FakeSyncer)
    assert svc.sync_account(store, "me@example.net", aid, full=True) == 4
    assert calls["mode"] == "full"
    assert svc.sync_account(store, "me@example.net", aid) == 1
    assert calls["mode"] == "inc"
    db.close()


def test_trash_message_imap(monkeypatch, tmp_path):
    from core.imap_client import imap_msg_key
    db = Database(tmp_path / "app.sqlite"); store = Store(db)
    aid = store.upsert_account("me@example.net", provider="imap")
    mid = store.upsert_message(aid, imap_msg_key("INBOX.Sent", 1000, 7),
                               subject="X", label_ids='["INBOX.Sent"]')
    fake = _FakeImapClient()
    monkeypatch.setattr(svc, "build_imap_client", lambda e: fake)
    svc.trash_message(store, "me@example.net", mid)
    assert ("select", "INBOX.Sent") in fake.events   # selects the right folder
    assert ("trash", 7) in fake.events
    assert dict(store.get_message(mid))["is_trashed"] == 1
    db.close()


def test_export_eml_imap(monkeypatch, tmp_path):
    db = Database(tmp_path / "app.sqlite"); store = Store(db)
    aid = store.upsert_account("me@example.net", provider="imap")
    mid = store.upsert_message(aid, "1000.7", subject="Fac", label_ids='["INBOX"]')
    monkeypatch.setattr(svc, "_imap_fetch_raw", lambda email, gid: b"RAW-IMAP")
    data, filename = svc.export_eml(store, mid)
    assert data == b"RAW-IMAP" and filename.endswith(".eml")
    db.close()


def _two_accounts_with_cache(tmp_path, monkeypatch):
    """Two accounts, each with a message and one cached attachment file."""
    db = Database(tmp_path / "data" / "maily.sqlite") if (tmp_path / "data").mkdir() is None else None
    store = Store(db)
    att_dir = tmp_path / "data" / "attachments"
    att_dir.mkdir()
    monkeypatch.setattr(svc.secrets_store, "delete_account_token", lambda email: None)
    out = {}
    for tag, email in (("one", "one@example.com"), ("two", "two@example.com")):
        out[tag] = {"aid": store.upsert_account(email)}
    # several mails per account, interleaved: they share database pages, as real mail does
    for i in range(8):
        for tag in ("one", "two"):
            aid = out[tag]["aid"]
            mid = store.upsert_message(
                aid, f"g-{tag}-{i}", subject=f"subject-{tag}-ZQXJ{tag}-{i}",
                snippet=f"snippet-{tag}-ZQXJ{tag}",
                body_text=f"body-{tag}-ZQXJ{tag} " + "lorem ipsum " * 20, addr_from="sender@example.org",
                label_ids='["INBOX"]')
            if i == 0:
                store.replace_attachments(mid, [{"filename": f"{tag}.txt", "mime_type": "text/plain",
                                                 "size": 5, "gmail_attachment_id": f"att-{tag}"}])
                att = store.list_attachments(mid)[0]["id"]
                path = att_dir / f"{att}_{tag}.txt"
                path.write_bytes(f"file-{tag}-ZQXJ{tag}".encode())
                store.set_attachment_path(att, str(path))
                out[tag].update({"mid": mid, "att": att, "path": path})
    return db, store, att_dir, out


def test_logout_deletes_the_attachment_files_of_the_account_only(monkeypatch, tmp_path):
    db, store, att_dir, acc = _two_accounts_with_cache(tmp_path, monkeypatch)
    orphan = att_dir / f"{acc['one']['att']}_renamed.bin"      # same id, other name
    orphan.write_bytes(b"x")
    svc.logout_account(store, acc["one"]["aid"], str(att_dir))
    assert not acc["one"]["path"].exists() and not orphan.exists()
    assert acc["two"]["path"].exists()
    assert store.list_attachments(acc["two"]["mid"])
    db.close()


@pytest.mark.skipif(not __import__("core.db", fromlist=["x"]).fts_secure_delete_supported(),
                    reason="SQLite older than 3.42")
def test_logout_leaves_no_trace_of_the_mail_in_the_data_folder(monkeypatch, tmp_path):
    db, store, att_dir, acc = _two_accounts_with_cache(tmp_path, monkeypatch)
    data = tmp_path / "data"
    # a real database has long been checkpointed: the text is in the main file
    assert db.checkpoint_truncate()
    # the strings are in the database file or its log before the disconnection
    before = b"".join(p.read_bytes() for p in data.rglob("*") if p.is_file())
    assert b"ZQXJone" in before
    assert b"zqxjone" in before.lower()
    svc.logout_account(store, acc["one"]["aid"], str(att_dir))
    after = b"".join(p.read_bytes() for p in data.rglob("*") if p.is_file())
    # the full-text index stores lower-case words: look for them too
    assert b"zqxjone" not in after.lower()
    assert b"ZQXJtwo" in after                                  # the other account is kept
    wal = data / "maily.sqlite-wal"
    assert (not wal.exists()) or wal.stat().st_size == 0
    # the full-text search of the other account still works, the first one's is empty
    assert len(store.search_messages("body-two-ZQXJtwo")) == 8
    assert store.search_messages("body-one-ZQXJone") == []
    db.close()


def test_logout_rebuilds_the_index_when_fts_secure_delete_is_missing(monkeypatch, tmp_path):
    db, store, att_dir, acc = _two_accounts_with_cache(tmp_path, monkeypatch)
    monkeypatch.setattr(db, "fts_secure_delete", False)
    rebuilt = []
    real = db.rebuild_fts
    monkeypatch.setattr(db, "rebuild_fts", lambda: (rebuilt.append(1), real())[1])
    svc.logout_account(store, acc["one"]["aid"], str(att_dir))
    assert rebuilt == [1]
    assert len(store.search_messages("body-two-ZQXJtwo")) == 8
    db.close()


def test_logout_never_deletes_a_file_outside_the_attachments_folder(monkeypatch, tmp_path):
    db, store, att_dir, acc = _two_accounts_with_cache(tmp_path, monkeypatch)
    outside = tmp_path / "precious.txt"
    outside.write_text("keep me")
    link_target = tmp_path / "target.txt"
    link_target.write_text("keep me too")
    (att_dir / f"{acc['one']['att']}_link").symlink_to(link_target)
    store.set_attachment_path(acc["one"]["att"], str(outside))          # trapped path
    traversal = att_dir / ".." / "precious.txt"
    store.set_attachment_path(acc["two"]["att"], str(traversal))
    svc.logout_account(store, acc["one"]["aid"], str(att_dir))
    svc.logout_account(store, acc["two"]["aid"], str(att_dir))
    assert outside.read_text() == "keep me"
    assert link_target.read_text() == "keep me too"                      # link removed, not target
    assert not (att_dir / f"{acc['one']['att']}_link").is_symlink()
    db.close()


def test_logout_erases_the_index_by_rebuilding_it_without_the_fts_option(monkeypatch, tmp_path):
    from core import db as dbmod
    monkeypatch.setattr(dbmod, "fts_secure_delete_supported", lambda: False)   # SQLite < 3.42
    db, store, att_dir, acc = _two_accounts_with_cache(tmp_path, monkeypatch)
    assert db.fts_secure_delete is False
    assert db.checkpoint_truncate()
    svc.logout_account(store, acc["one"]["aid"], str(att_dir))
    after = b"".join(p.read_bytes() for p in (tmp_path / "data").rglob("*") if p.is_file())
    assert b"zqxjone" not in after.lower()
    assert len(store.search_messages("body-two-ZQXJtwo")) == 8
    db.close()
