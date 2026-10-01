"""Trashing an IMAP message never deletes it unless it is safely in the trash.

ImapClient runs against a fake imaplib connection (no network)."""
import pytest
from fastapi.testclient import TestClient

from core import accounts_service as svc
from core.imap_client import ImapClient, ImapError, NoTrashFolder, imap_msg_key, parse_list_line
from core.store import Store


class FakeConn:
    """Answers LIST / UID like imaplib: NO responses are returned, not raised."""

    def __init__(self, folders, move="OK", copy="OK", capabilities=("IMAP4REV1",), list_error=False):
        self.folders, self.move, self.copy = folders, move, copy
        self.capabilities = capabilities
        self.list_error = list_error
        self.calls = []

    def list(self):
        if self.list_error:
            import imaplib
            raise imaplib.IMAP4.error("LIST failed")
        return "OK", list(self.folders)

    def uid(self, command, *args):
        self.calls.append((command,) + args)
        if command == "MOVE":
            return self.move, [None]
        if command == "COPY":
            return self.copy, [None]
        return "OK", [None]

    def expunge(self):
        self.calls.append(("EXPUNGE-ALL",))
        return "OK", [None]


def _client(conn):
    c = ImapClient("imap.example.net", 993, "me@example.net", "pw")
    c.conn = conn
    return c


def _deleting(calls):
    return [c for c in calls if c[0] in ("STORE", "EXPUNGE", "EXPUNGE-ALL")]


def test_special_use_trash_folder_is_preferred():
    conn = FakeConn([rb'(\HasNoChildren) "/" INBOX', rb'(\Trash \HasNoChildren) "/" "Papierkorb"',
                     rb'(\HasNoChildren) "/" Trash'])
    _client(conn).move_to_trash(7)
    assert conn.calls == [("MOVE", "7", '"Papierkorb"')]


def test_usual_name_is_used_without_special_use():
    conn = FakeConn([rb'(\HasNoChildren) "." INBOX', rb'(\HasNoChildren) "." "INBOX.Trash"'])
    _client(conn).move_to_trash(7)
    assert conn.calls == [("MOVE", "7", '"INBOX.Trash"')]


@pytest.mark.parametrize("folders", [
    [rb'(\HasNoChildren) "/" INBOX', rb'(\HasNoChildren) "/" Sent'],
    # names that only contain "Trash" are not a trash folder (no substring match)
    [rb'(\HasNoChildren) "/" INBOX', rb'(\HasNoChildren) "/" "Trash Archive"'],
    # a non-selectable container cannot receive messages
    [rb'(\Noselect \Trash) "/" Trash'],
    [],
])
def test_no_trash_folder_refuses_and_touches_nothing(folders):
    conn = FakeConn(folders)
    with pytest.raises(NoTrashFolder) as exc:
        _client(conn).move_to_trash(7)
    assert str(exc.value) == "no trash folder on this IMAP account" and exc.value.code == "no_trash_folder"
    assert conn.calls == []


def test_failed_listing_refuses_and_touches_nothing():
    conn = FakeConn([], list_error=True)
    with pytest.raises(ImapError):
        _client(conn).move_to_trash(7)
    assert conn.calls == []


def test_copy_fallback_expunges_only_this_message_with_uidplus():
    conn = FakeConn([rb'(\HasNoChildren) "/" Trash'], move="NO", capabilities=("IMAP4REV1", "UIDPLUS"))
    _client(conn).move_to_trash(7)
    assert conn.calls == [("MOVE", "7", '"Trash"'), ("COPY", "7", '"Trash"'),
                          ("STORE", "7", "+FLAGS", "(\\Deleted)"), ("EXPUNGE", "7")]


def test_copy_fallback_without_uidplus_uses_expunge():
    conn = FakeConn([rb'(\HasNoChildren) "/" Trash'], move="NO")
    _client(conn).move_to_trash(7)
    assert conn.calls[-1] == ("EXPUNGE-ALL",)


def test_refused_copy_never_deletes():
    conn = FakeConn([rb'(\HasNoChildren) "/" Trash'], move="NO", copy="NO")
    with pytest.raises(ImapError):
        _client(conn).move_to_trash(7)
    assert _deleting(conn.calls) == []


def test_list_line_parser_handles_quoted_and_unquoted_names():
    assert parse_list_line(rb'(\Trash \HasNoChildren) "/" Trash') == ({"\\trash", "\\hasnochildren"}, "Trash")
    assert parse_list_line(rb'() "." "INBOX.Sent Items"') == (set(), "INBOX.Sent Items")
    assert parse_list_line(rb'() NIL INBOX') == (set(), "INBOX")
    assert parse_list_line(rb'() "/" "a\"b"') == (set(), 'a"b')
    assert parse_list_line(("literal", b"x")) is None


def test_list_folders_reads_unquoted_names():
    conn = FakeConn([rb'(\HasNoChildren) "/" INBOX', rb'(\HasNoChildren) "/" Archive',
                     rb'(\Noselect) "/" Folders'])
    assert _client(conn).list_folders() == ["INBOX", "Archive"]


def _imap_message(store):
    aid = store.upsert_account("me@example.net", provider="imap")
    return store.upsert_message(aid, imap_msg_key("INBOX", 1000, 7), subject="X", label_ids='["INBOX"]')


class _NoTrashClient:
    def connect(self): return self
    def select_folder(self, name): return 1000
    def move_to_trash(self, uid): raise NoTrashFolder()
    def logout(self): pass


def test_engine_leaves_the_message_untouched(monkeypatch, database):
    store = Store(database)
    mid = _imap_message(store)
    monkeypatch.setattr(svc, "build_imap_client", lambda e: _NoTrashClient())
    with pytest.raises(NoTrashFolder):
        svc.trash_message(store, "me@example.net", mid)
    assert dict(store.get_message(mid))["is_trashed"] == 0


def test_api_answers_a_stable_code(database):
    from api.app import create_app

    def act(message_id, action, add=None, remove=None):
        raise NoTrashFolder()

    c = TestClient(create_app(Store(database), "tok", act_fn=act))
    r = c.post("/messages/1/trash", headers={"Authorization": "Bearer tok"})
    assert r.status_code == 409
    assert r.headers["x-maily-error"] == "no_trash_folder"
    assert r.json()["detail"] == "no trash folder on this IMAP account"


def test_mcp_tool_reports_the_refusal(monkeypatch, database):
    pytest.importorskip("mcp")
    from app import mcp_server as S
    store = Store(database)
    mid = _imap_message(store)
    monkeypatch.setattr(S, "_store", store)
    monkeypatch.setattr(svc, "build_imap_client", lambda e: _NoTrashClient())
    out = S.maily_trash(mid)
    assert out["code"] == "no_trash_folder" and "no trash folder" in out["error"]
    assert dict(store.get_message(mid))["is_trashed"] == 0
