"""Guard in code of maily_send and maily_trash (MA-1, lot 1a).

The server is driven through the MCP SDK's in-memory client, with and without
an elicitation callback. Nothing touches the network: `send_from_account` and
`trash_message` are replaced, and the data folder is a temporary one (conftest).
"""
import asyncio
import json
import os
import sqlite3
import stat
import threading
import time
from types import SimpleNamespace

import pytest

pytest.importorskip("mcp")
from mcp import types  # noqa: E402
from mcp.shared.memory import create_connected_server_and_client_session  # noqa: E402

from app import mcp_server as S  # noqa: E402
from core import accounts_service, mcp_guard  # noqa: E402


class FakeStore:
    def __init__(self):
        self._accounts = [
            {"id": 1, "email": "alex@example.com", "display_name": "Personal", "color": "#fb7185"},
        ]
        self._messages = {
            7: {"id": 7, "account_id": 1, "addr_from": "sam@example.net",
                "subject": "Invoice", "internal_date": 1_700_000_000_000},
        }

    def list_accounts(self):
        return [dict(a) for a in self._accounts]

    def get_message(self, mid):
        return dict(self._messages[mid]) if mid in self._messages else None

    def get_account(self, aid):
        return next((dict(a) for a in self._accounts if a["id"] == aid), None)


@pytest.fixture(autouse=True)
def env_and_fakes(monkeypatch):
    for var in ("MAILY_ALLOW_SEND", "MAILY_ALLOW_TRASH",
                "MAILY_MCP_MAX_SENDS_PER_HOUR", "MAILY_MCP_MAX_TRASH_PER_HOUR"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(S, "_store", FakeStore())
    calls = SimpleNamespace(sent=[], trashed=[], fail=None)

    def fake_send(store, email, account_id, payload):
        if calls.fail:
            raise calls.fail
        calls.sent.append(payload)
        return {"id": "gmail-1"}

    def fake_trash(store, email, message_id):
        if calls.fail:
            raise calls.fail
        calls.trashed.append(message_id)

    monkeypatch.setattr(accounts_service, "send_from_account", fake_send)
    monkeypatch.setattr(accounts_service, "trash_message", fake_trash)
    return calls


SEND = {"profile": "alex@example.com", "to": "sam@example.net",
        "subject": "Hello", "body_text": "Body of the mail"}


def call(tool, args, callback=None):
    """Runs one tool call through an in-memory client. Returns the result dict."""
    async def run():
        async with create_connected_server_and_client_session(
                S.mcp, elicitation_callback=callback) as client:
            res = await client.call_tool(tool, args)
            if res.structuredContent is not None:
                return res.structuredContent
            return json.loads(res.content[0].text)
    return asyncio.run(run())


def answer(action, confirm=True, seen=None):
    async def cb(context, params):
        if seen is not None:
            seen.append(params)
        if action == "accept":
            return types.ElicitResult(action="accept", content={"confirm": confirm})
        return types.ElicitResult(action=action)
    return cb


def journal_rows():
    path = mcp_guard.db_path()
    if not path.exists():
        return []
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM mcp_guard_log ORDER BY id")]
    finally:
        conn.close()


# --- CA1: the human's agreement through elicitation ---------------------------

def test_send_accepted_through_elicitation(env_and_fakes):
    seen = []
    out = call("maily_send", SEND, answer("accept", seen=seen))
    assert out["sent_from"] == "alex@example.com"
    assert len(env_and_fakes.sent) == 1
    # The box shows the profile, the recipient, the subject and the start of the body.
    msg = seen[0].message
    for needle in ("alex@example.com", "sam@example.net", "Hello", "Body of the mail"):
        assert needle in msg
    # A flat schema: one boolean.
    props = seen[0].requestedSchema["properties"]
    assert list(props) == ["confirm"] and props["confirm"]["type"] == "boolean"
    rows = journal_rows()
    assert rows[-1]["decision"] == "sent" and rows[-1]["approval"] == "elicitation"


@pytest.mark.parametrize("cb, code, decision", [
    (answer("accept", confirm=False), "declined", "declined"),
    (answer("decline"), "declined", "declined"),
    (answer("cancel"), "cancelled", "cancelled"),
])
def test_send_refused_by_the_human(env_and_fakes, cb, code, decision):
    out = call("maily_send", SEND, cb)
    assert out["code"] == code and "error" in out and "detail" in out
    assert env_and_fakes.sent == []
    assert journal_rows()[-1]["decision"] == decision


def test_elicitation_error_is_a_refusal(env_and_fakes):
    async def broken(context, params):
        return types.ErrorData(code=types.INTERNAL_ERROR, message="boom")
    out = call("maily_send", SEND, broken)
    assert out["code"] == "confirmation_unavailable"
    assert env_and_fakes.sent == []
    assert journal_rows()[-1]["decision"] == "error"
    assert journal_rows()[-1]["counted"] == 0


def test_elicitation_timeout_is_a_refusal(env_and_fakes, monkeypatch):
    monkeypatch.setattr(mcp_guard, "CONFIRM_TIMEOUT_SECONDS", 0.2)

    async def slow(context, params):
        await asyncio.sleep(5)
        return types.ElicitResult(action="accept", content={"confirm": True})
    out = call("maily_send", SEND, slow)
    assert out["code"] == "cancelled"
    assert env_and_fakes.sent == []
    assert journal_rows()[-1]["decision"] == "cancelled"


def test_refusal_by_elicitation_never_falls_back_to_the_variable(env_and_fakes, monkeypatch):
    monkeypatch.setenv("MAILY_ALLOW_SEND", "1")
    out = call("maily_send", SEND, answer("decline"))
    assert out["code"] == "declined"
    assert env_and_fakes.sent == []


# --- CA2: no elicitation, then the variable -----------------------------------

def test_no_elicitation_and_no_variable_refuses(env_and_fakes):
    out = call("maily_send", SEND)
    assert out["code"] == "confirmation_unavailable"
    assert "MAILY_ALLOW_SEND=1" in out["detail"]
    assert env_and_fakes.sent == []
    assert journal_rows()[-1]["decision"] == "refused_disabled"


def test_no_elicitation_with_the_variable_passes(env_and_fakes, monkeypatch):
    monkeypatch.setenv("MAILY_ALLOW_SEND", "1")
    out = call("maily_send", SEND)
    assert out["sent_from"] == "alex@example.com"
    assert len(env_and_fakes.sent) == 1
    assert journal_rows()[-1]["approval"] == "env"


@pytest.mark.parametrize("value", ["0", "true", "yes", ""])
def test_only_one_enables(env_and_fakes, monkeypatch, value):
    monkeypatch.setenv("MAILY_ALLOW_SEND", value)
    assert call("maily_send", SEND)["code"] == "confirmation_unavailable"


def test_send_variable_does_not_enable_trash(env_and_fakes, monkeypatch):
    monkeypatch.setenv("MAILY_ALLOW_SEND", "1")
    out = call("maily_trash", {"message_id": 7})
    assert out["code"] == "confirmation_unavailable" and "MAILY_ALLOW_TRASH=1" in out["detail"]
    assert env_and_fakes.trashed == []


def _ctx(elicitation):
    caps = SimpleNamespace(elicitation=elicitation)
    return SimpleNamespace(session=SimpleNamespace(
        client_params=SimpleNamespace(capabilities=caps)))


def test_capability_form_empty_or_absent():
    assert mcp_guard.supports_form_elicitation(_ctx(types.ElicitationCapability())) is True
    assert mcp_guard.supports_form_elicitation(
        _ctx(types.ElicitationCapability(form=types.FormElicitationCapability()))) is True
    assert mcp_guard.supports_form_elicitation(_ctx(None)) is False
    assert mcp_guard.supports_form_elicitation(SimpleNamespace(session=None)) is False


def test_capability_without_form_and_url_fields_counts_as_form():
    """B1: an older SDK's ElicitationCapability has neither field."""
    assert mcp_guard.supports_form_elicitation(_ctx(SimpleNamespace())) is True


def test_url_only_capability_counts_as_absent(env_and_fakes, monkeypatch):
    original = types.ElicitationCapability
    url_only = original(url=types.UrlElicitationCapability())
    assert mcp_guard.supports_form_elicitation(_ctx(url_only)) is False
    # Through the tool: a client that declares `url` only (and would answer
    # "accept") is treated as having no elicitation, so it is refused.
    monkeypatch.setattr(types, "ElicitationCapability",
                        lambda **kw: original(url=types.UrlElicitationCapability()))
    asked = []
    out = call("maily_send", SEND, answer("accept", seen=asked))
    assert out["code"] == "confirmation_unavailable"
    assert asked == [] and env_and_fakes.sent == []


# --- CA3: limits that do not depend on the client -----------------------------

def test_six_recipients_refused(env_and_fakes, monkeypatch):
    monkeypatch.setenv("MAILY_ALLOW_SEND", "1")
    args = dict(SEND, to="a@x.org, b@x.org, c@x.org", cc="d@x.org,e@x.org, f@x.org")
    out = call("maily_send", args)
    assert out["code"] == "too_many_recipients"
    assert env_and_fakes.sent == []
    assert journal_rows()[-1]["decision"] == "refused_cap"
    # Five is fine.
    args["cc"] = "d@x.org,e@x.org"
    assert "sent_from" in call("maily_send", args)


def test_recipient_count_respects_quoted_names():
    assert mcp_guard.count_recipients('"Doe, John" <j@x.org>, k@x.org', "l@x.org") == 3
    assert mcp_guard.count_recipients("a@x.org", None) == 1
    with pytest.raises(mcp_guard.UnreadableRecipients):
        mcp_guard.count_recipients(None, None)


SIX = "a@x.com, b@x.com, c@x.com, d@x.com, e@x.com, f@x.com"
TRICKY = [
    SIX,
    f"<{SIX}>",
    f"{SIX} (x",
    'a@x.com"", b@x.com, c@x.com, d@x.com, e@x.com, f@x.com',
    "=?utf-8?q?a=40x.com=2C_b=40x.com?= <z@x.com>, c@x.com, d@x.com, e@x.com, f@x.com, g@x.com",
]


@pytest.mark.parametrize("to", TRICKY)
def test_recipient_cap_holds_for_strings_the_parsers_read_differently(
        env_and_fakes, monkeypatch, to):
    """H1: the count uses the parser that builds the message, and anything it
    reads with a defect is refused: nothing goes out."""
    from core import mime
    monkeypatch.setenv("MAILY_ALLOW_SEND", "1")
    out = call("maily_send", dict(SEND, to=to))
    assert out.get("code") == "too_many_recipients", out
    assert env_and_fakes.sent == []
    # What the guard let through is what the message carries.
    raw, _ = mime.build_mime("alex@example.com", "a@x.org, b@x.org", "s", "b")
    assert raw


@pytest.mark.parametrize("to", ["", "   ", "garbage", "undisclosed-recipients:;",
                                "a@x.com\r\nBcc: z@x.com"])
def test_unreadable_recipients_are_refused(env_and_fakes, monkeypatch, to):
    monkeypatch.setenv("MAILY_ALLOW_SEND", "1")
    out = call("maily_send", dict(SEND, to=to))
    assert out.get("code") == "too_many_recipients", out
    assert env_and_fakes.sent == []


def test_five_ordinary_addresses_still_go(env_and_fakes, monkeypatch):
    monkeypatch.setenv("MAILY_ALLOW_SEND", "1")
    to = '"Doe, John" <a@x.com>, b@x.com, c@x.com, d@x.com, e@x.com'
    assert "sent_from" in call("maily_send", dict(SEND, to=to))
    assert len(env_and_fakes.sent) == 1


def test_count_matches_the_message_built_for_sending():
    from email import message_from_bytes, policy
    import base64
    from core import mime
    to, cc = '"Doe, John" <a@x.com>, b@x.com', "c@x.com"
    raw, _ = mime.build_mime("me@x.com", to, "s", "b", cc=cc)
    msg = message_from_bytes(base64.urlsafe_b64decode(raw), policy=policy.default)
    sent = len(msg["To"].addresses) + len(msg["Cc"].addresses)
    assert mcp_guard.count_recipients(to, cc) == sent == 3


# --- CA2: the box shows what will go out ---------------------------------------

def test_box_shows_the_real_address_behind_a_long_display_name():
    to = '"sam@example.net' + " " * 490 + '" <attacker@evil.example>'
    text = mcp_guard.describe_send("alex@example.com", to, None, "Hi", "Body")
    assert "attacker@evil.example" in text
    assert "sam@example.net" not in text


def test_box_lists_addresses_and_short_names_after_them():
    text = mcp_guard.describe_send(
        "alex@example.com", '"Doe John" <j@x.org>, k@x.org', "l@x.org, m@x.org", "Hi", "B")
    assert "To: j@x.org (Doe John), k@x.org\n" in text
    assert "Cc: l@x.org, m@x.org\n" in text


def test_box_drops_a_name_that_stages_an_address():
    text = mcp_guard.describe_send(
        "alex@example.com", '"x@good.org" <attacker@evil.example>', None, "Hi", "B")
    assert "good.org" not in text and "attacker@evil.example" in text


def test_through_the_tool_the_box_has_the_real_address(env_and_fakes):
    seen = []
    to = '"sam@example.net' + " " * 490 + '" <attacker@evil.example>'
    call("maily_send", dict(SEND, to=to), answer("accept", seen=seen))
    assert "attacker@evil.example" in seen[0].message


# --- M1: the body is shown far enough, and the cut says so ---------------------

def test_long_body_says_what_is_not_shown():
    text = mcp_guard.describe_send("a@x.org", "b@x.org", None, "S", "x" * 5000)
    assert "x" * 4000 in text and "x" * 4001 not in text
    assert "(+1000 characters not shown)" in text


def test_short_body_is_shown_whole_and_blank_runs_are_squeezed():
    body = "start" + "\n \n" * 500 + "end"
    text = mcp_guard.describe_send("a@x.org", "b@x.org", None, "S", body)
    assert "end" in text and "not shown" not in text
    assert text.count("\n") < 15


def test_eleventh_send_in_an_hour_refused(env_and_fakes, monkeypatch):
    monkeypatch.setenv("MAILY_ALLOW_SEND", "1")
    for _ in range(10):
        assert "sent_from" in call("maily_send", SEND)
    out = call("maily_send", SEND)
    assert out["code"] == "rate_limited"
    assert len(env_and_fakes.sent) == 10


def test_the_limit_applies_with_elicitation_too(env_and_fakes):
    for _ in range(10):
        assert "sent_from" in call("maily_send", SEND, answer("accept"))
    assert call("maily_send", SEND, answer("accept"))["code"] == "rate_limited"


def test_declined_sends_do_not_use_the_hour(env_and_fakes):
    for _ in range(12):
        assert call("maily_send", SEND, answer("decline"))["code"] == "declined"
    assert "sent_from" in call("maily_send", SEND, answer("accept"))


def test_a_failed_send_still_uses_its_slot(env_and_fakes, monkeypatch):
    monkeypatch.setenv("MAILY_ALLOW_SEND", "1")
    monkeypatch.setenv("MAILY_MCP_MAX_SENDS_PER_HOUR", "2")
    env_and_fakes.fail = RuntimeError("network down")
    assert "sending failed" in call("maily_send", SEND)["error"]
    assert "sending failed" in call("maily_send", SEND)["error"]
    assert call("maily_send", SEND)["code"] == "rate_limited"
    assert [r["decision"] for r in journal_rows()][:2] == ["error", "error"]


def test_old_sends_leave_the_window(env_and_fakes, monkeypatch):
    monkeypatch.setenv("MAILY_ALLOW_SEND", "1")
    monkeypatch.setenv("MAILY_MCP_MAX_SENDS_PER_HOUR", "1")
    assert "sent_from" in call("maily_send", SEND)
    assert call("maily_send", SEND)["code"] == "rate_limited"
    conn = sqlite3.connect(str(mcp_guard.db_path()))
    conn.execute("UPDATE mcp_guard_log SET ts = ?", (time.time() - 3700,))
    conn.commit()
    conn.close()
    assert "sent_from" in call("maily_send", SEND)


def test_limits_can_only_be_lowered(monkeypatch):
    assert mcp_guard._limit("maily_send") == 10
    assert mcp_guard._limit("maily_trash") == 30
    monkeypatch.setenv("MAILY_MCP_MAX_SENDS_PER_HOUR", "3")
    assert mcp_guard._limit("maily_send") == 3
    monkeypatch.setenv("MAILY_MCP_MAX_SENDS_PER_HOUR", "500")
    assert mcp_guard._limit("maily_send") == 10
    monkeypatch.setenv("MAILY_MCP_MAX_SENDS_PER_HOUR", "lots")
    assert mcp_guard._limit("maily_send") == 10
    monkeypatch.setenv("MAILY_MCP_MAX_SENDS_PER_HOUR", "-4")
    assert mcp_guard._limit("maily_send") == 0


def test_trash_limit_is_thirty(env_and_fakes, monkeypatch):
    monkeypatch.setenv("MAILY_ALLOW_TRASH", "1")
    for _ in range(30):
        assert call("maily_trash", {"message_id": 7}).get("trashed") == 7
    assert call("maily_trash", {"message_id": 7})["code"] == "rate_limited"
    assert len(env_and_fakes.trashed) == 30


def test_two_connections_cannot_both_slip_under_the_limit(monkeypatch):
    """Ten threads, each with its own SQLite connection, ask for a slot with a
    limit of 4: exactly 4 get one (count and insert are one transaction)."""
    monkeypatch.setenv("MAILY_MCP_MAX_SENDS_PER_HOUR", "4")
    results, barrier = [], threading.Barrier(10)

    def worker():
        barrier.wait()
        try:
            mcp_guard.reserve("maily_send", "alex@example.com", "x@y.org", "s")
            results.append("ok")
        except mcp_guard.Refusal as r:
            results.append(r.code)

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results.count("ok") == 4
    assert results.count("rate_limited") == 6


def test_journal_unavailable_fails_closed(env_and_fakes, monkeypatch):
    monkeypatch.setenv("MAILY_ALLOW_SEND", "1")
    blocker = mcp_guard.paths.runtime_dir() / "blocker"
    blocker.parent.mkdir(parents=True, exist_ok=True)
    blocker.write_text("a file where a folder is needed")
    monkeypatch.setattr(mcp_guard, "db_path", lambda: blocker / "mcp_guard.sqlite")
    out = call("maily_send", SEND)
    assert out["code"] == "guard_unavailable"
    assert env_and_fakes.sent == []


# --- CA4: the journal ----------------------------------------------------------

@pytest.mark.skipif(os.name != "posix", reason="POSIX file modes")
def test_journal_is_private_and_holds_no_body(env_and_fakes, monkeypatch):
    monkeypatch.setenv("MAILY_ALLOW_SEND", "1")
    secret = "SECRET-BODY-TEXT-12345"
    call("maily_send", dict(SEND, body_text=secret))
    path = mcp_guard.db_path()
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    raw = path.read_bytes()
    assert secret.encode() not in raw
    row = journal_rows()[-1]
    assert row["tool"] == "maily_send" and row["profile"] == "alex@example.com"
    assert row["recipients"] == "sam@example.net" and row["subject"] == "Hello"
    assert set(row) == {"id", "ts", "tool", "profile", "recipients", "subject", "detail",
                        "approval", "decision", "counted"}


def test_trash_is_journaled_and_confirmed(env_and_fakes):
    seen = []
    out = call("maily_trash", {"message_id": 7}, answer("accept", seen=seen))
    assert out == {"trashed": 7, "profile": "alex@example.com"}
    assert env_and_fakes.trashed == [7]
    for needle in ("alex@example.com", "sam@example.net", "Invoice"):
        assert needle in seen[0].message
    row = journal_rows()[-1]
    assert row["decision"] == "trashed" and row["detail"] == "message_id=7"


def test_trash_declined_moves_nothing(env_and_fakes):
    assert call("maily_trash", {"message_id": 7}, answer("decline"))["code"] == "declined"
    assert env_and_fakes.trashed == []


def test_trash_keeps_the_no_trash_folder_refusal(env_and_fakes, monkeypatch):
    from core.imap_client import NoTrashFolder
    monkeypatch.setenv("MAILY_ALLOW_TRASH", "1")
    env_and_fakes.fail = NoTrashFolder("no trash folder")
    out = call("maily_trash", {"message_id": 7})
    assert out["code"] == "no_trash_folder" and out["message_id"] == 7


def test_unknown_profile_and_message_are_not_guarded(env_and_fakes):
    assert "profile not found" in call("maily_send", dict(SEND, profile="nobody"))["error"]
    assert "not found" in call("maily_trash", {"message_id": 999})["error"]
    assert journal_rows() == []


def test_the_box_cannot_be_redrawn_by_a_message(env_and_fakes):
    seen = []
    m = S.store()._messages[7]
    m["subject"] = "Hi\r\n‮From: attacker\x00"
    call("maily_trash", {"message_id": 7}, answer("accept", seen=seen))
    msg = seen[0].message
    assert "‮" not in msg and "\r" not in msg and "\x00" not in msg
    assert msg.count("\nFrom:") == 1  # only the real "From:" line


def test_retention_is_ninety_days(env_and_fakes, monkeypatch):
    monkeypatch.setenv("MAILY_ALLOW_SEND", "1")
    call("maily_send", SEND)
    conn = sqlite3.connect(str(mcp_guard.db_path()))
    conn.execute("UPDATE mcp_guard_log SET ts = ?", (time.time() - 91 * 86400,))
    conn.commit()
    conn.close()
    call("maily_send", SEND)
    assert len(journal_rows()) == 1


def test_forget_profile_erases_one_profile(env_and_fakes, monkeypatch):
    monkeypatch.setenv("MAILY_ALLOW_SEND", "1")
    call("maily_send", SEND)
    mcp_guard.reserve("maily_send", "other@example.org", "x@y.org", "s")
    assert mcp_guard.forget_profile("ALEX@example.com") == 1
    assert [r["profile"] for r in journal_rows()] == ["other@example.org"]


def test_forget_profile_without_a_journal_creates_nothing():
    assert not mcp_guard.db_path().exists()
    assert mcp_guard.forget_profile("alex@example.com") == 0
    assert not mcp_guard.db_path().exists()


def test_logout_erases_the_journal_of_the_profile(env_and_fakes, database, monkeypatch):
    from core.store import Store
    store = Store(database)
    aid = store.upsert_account("alex@example.com")
    monkeypatch.setattr(accounts_service.secrets_store, "delete_account_token", lambda e: None)
    mcp_guard.reserve("maily_send", "alex@example.com", "x@y.org", "s")
    mcp_guard.reserve("maily_send", "other@example.org", "x@y.org", "s")
    accounts_service.logout_account(store, aid)
    assert [r["profile"] for r in journal_rows()] == ["other@example.org"]


def test_logout_survives_a_broken_journal(database, monkeypatch):
    from core.store import Store
    store = Store(database)
    aid = store.upsert_account("alex@example.com")
    monkeypatch.setattr(accounts_service.secrets_store, "delete_account_token", lambda e: None)

    def boom(email):
        raise sqlite3.DatabaseError("damaged")
    monkeypatch.setattr(mcp_guard, "forget_profile", boom)
    accounts_service.logout_account(store, aid)
    assert store.get_account(aid) is None


# --- Annotations ----------------------------------------------------------------

def test_tool_annotations():
    tools = {t.name: t for t in asyncio.run(S.mcp.list_tools())}
    for name in ("maily_send", "maily_trash"):
        a = tools[name].annotations
        assert a.destructiveHint is True and a.readOnlyHint is False
    for name in ("maily_list_accounts", "maily_list_messages", "maily_get_message",
                 "maily_search"):
        assert tools[name].annotations.readOnlyHint is True
    # The context is injected by the SDK: it is not a parameter of the tools.
    assert "ctx" not in tools["maily_send"].inputSchema["properties"]
    assert "ctx" not in tools["maily_trash"].inputSchema["properties"]
