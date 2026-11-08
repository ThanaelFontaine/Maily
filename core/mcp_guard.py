"""Guard in code for the two MCP tools that change a mailbox: `maily_send` and
`maily_trash` (audit finding MA-1).

Before this module, the only confirmation was a sentence in the description of
the tools: text the model reads, not a control. Three layers now, in this order
(see docs/MCP.md and SECURITY.md):

1. Limits that do not depend on the client: at most MAX_RECIPIENTS addresses
   per message, and a number of sends and of trashes per sliding hour for the
   whole installation. They can be lowered with MAILY_MCP_MAX_SENDS_PER_HOUR and
   MAILY_MCP_MAX_TRASH_PER_HOUR, never raised.
2. The human's agreement. If the client declares form elicitation, the server
   asks through `ctx.elicit` and only an explicit "accept" with the box ticked
   goes on: decline, cancel, an error or a timeout end the call, and never fall
   back to the environment variable. A client without elicitation is refused,
   unless the owner set MAILY_ALLOW_SEND=1 (resp. MAILY_ALLOW_TRASH=1) in the
   environment of the server: a permanent agreement, written in the config of
   the client.
3. A journal of every attempt (`mcp_guard.sqlite`, mode 0600, never a body),
   kept 90 days and erased per profile when the account is disconnected.

The journal is a file of its own and not a table of the main database: the app
and the MCP server migrate that one in parallel. Counting the hour and writing
the reservation happen in one `BEGIN IMMEDIATE` transaction, so two MCP servers
started by two clients cannot both slip under the limit.
"""
from __future__ import annotations
import asyncio
import contextlib
import logging
import os
import pathlib
import re
import sqlite3
import time
import unicodedata
from email.message import EmailMessage
from typing import Callable

from core import paths

log = logging.getLogger("maily.mcp_guard")

MAX_RECIPIENTS = 5
DEFAULT_MAX_SENDS_PER_HOUR = 10
DEFAULT_MAX_TRASH_PER_HOUR = 30
WINDOW_SECONDS = 3600
RETENTION_DAYS = 90
# How long the human has to answer the confirmation box.
CONFIRM_TIMEOUT_SECONDS = 300

ENV_ALLOW = {"maily_send": "MAILY_ALLOW_SEND", "maily_trash": "MAILY_ALLOW_TRASH"}
ENV_LIMIT = {"maily_send": "MAILY_MCP_MAX_SENDS_PER_HOUR",
             "maily_trash": "MAILY_MCP_MAX_TRASH_PER_HOUR"}
_DEFAULT_LIMIT = {"maily_send": DEFAULT_MAX_SENDS_PER_HOUR,
                  "maily_trash": DEFAULT_MAX_TRASH_PER_HOUR}
_DONE = {"maily_send": "sent", "maily_trash": "trashed"}

# Codes of the refusals returned to the client.
CONFIRMATION_UNAVAILABLE = "confirmation_unavailable"
DECLINED = "declined"
CANCELLED = "cancelled"
TOO_MANY_RECIPIENTS = "too_many_recipients"
RATE_LIMITED = "rate_limited"
GUARD_UNAVAILABLE = "guard_unavailable"


class Refusal(Exception):
    """The guard says no: nothing is sent or moved. `decision` is what the
    journal records."""

    def __init__(self, code: str, detail: str, decision: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.decision = decision

    def as_tool_result(self) -> dict:
        return {"error": _ERRORS.get(self.code, "refused"), "code": self.code,
                "detail": self.detail}


_ERRORS = {
    CONFIRMATION_UNAVAILABLE: "no confirmation from the user: nothing was done",
    DECLINED: "the user declined: nothing was done",
    CANCELLED: "the confirmation was cancelled: nothing was done",
    TOO_MANY_RECIPIENTS: "too many recipients: nothing was sent",
    RATE_LIMITED: "hourly limit reached: nothing was done",
    GUARD_UNAVAILABLE: "the safety journal cannot be used: nothing was done",
}


# --- The journal --------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS mcp_guard_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ts         REAL    NOT NULL,
    tool       TEXT    NOT NULL,
    profile    TEXT,
    recipients TEXT,
    subject    TEXT,
    detail     TEXT,
    approval   TEXT,
    decision   TEXT    NOT NULL,
    counted    INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS mcp_guard_log_tool_ts ON mcp_guard_log (tool, ts);
CREATE INDEX IF NOT EXISTS mcp_guard_log_profile ON mcp_guard_log (profile);
"""


def db_path() -> pathlib.Path:
    return paths.runtime_dir() / "mcp_guard.sqlite"


def _create_private(path: pathlib.Path) -> None:
    """Creates the journal file with mode 0600 before SQLite opens it (SQLite
    gives its side files, the rollback journal, the mode of the main file)."""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(str(path), os.O_RDWR | os.O_CREAT, 0o600)
    os.close(fd)
    if os.name == "posix":
        os.chmod(path, 0o600)


@contextlib.contextmanager
def _journal(create: bool = True):
    """Opens the journal (autocommit: transactions are explicit). `create=False`
    yields None when the file does not exist yet."""
    path = db_path()
    if not path.exists():
        if not create:
            yield None
            return
        _create_private(path)
    conn = sqlite3.connect(str(path), timeout=5.0, isolation_level=None)
    try:
        conn.row_factory = sqlite3.Row
        conn.executescript(_SCHEMA)
        yield conn
    finally:
        conn.close()


def _clip(value, limit: int):
    if value is None:
        return None
    return str(value)[:limit]


def _limit(tool: str) -> int:
    """The hourly limit: the default, or a lower value from the environment. A
    value above the default, or one that is not a number, changes nothing."""
    default = _DEFAULT_LIMIT[tool]
    raw = os.environ.get(ENV_LIMIT[tool], "").strip()
    if not raw:
        return default
    try:
        return max(0, min(default, int(raw)))
    except ValueError:
        return default


def _insert(conn, tool, profile, recipients, subject, detail, approval,
            decision, counted) -> int:
    cur = conn.execute(
        "INSERT INTO mcp_guard_log (ts, tool, profile, recipients, subject, detail,"
        " approval, decision, counted) VALUES (?,?,?,?,?,?,?,?,?)",
        (time.time(), tool, _clip(profile, 320), _clip(recipients, 1000),
         _clip(subject, 300), _clip(detail, 200), approval, decision, counted))
    return cur.lastrowid


def log_refusal(tool, profile, recipients, subject, detail, decision: str) -> None:
    """Journals an attempt stopped before it counts (never raises)."""
    try:
        with _journal() as conn:
            _insert(conn, tool, profile, recipients, subject, detail, None, decision, 0)
    except Exception:
        log.warning("could not write the MCP guard journal", exc_info=True)


def reserve(tool: str, profile, recipients, subject, detail=None) -> int:
    """Takes one slot of the hourly limit for `tool` (sliding window, whole
    installation) and journals the attempt as "pending". Raises Refusal
    (rate_limited, or guard_unavailable when the journal cannot be used: the
    guard fails closed). Returns the id of the journal row."""
    limit = _limit(tool)
    now = time.time()
    try:
        with _journal() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute("DELETE FROM mcp_guard_log WHERE ts < ?",
                             (now - RETENTION_DAYS * 86400,))
                used = conn.execute(
                    "SELECT COUNT(*) FROM mcp_guard_log"
                    " WHERE tool = ? AND counted = 1 AND ts >= ?",
                    (tool, now - WINDOW_SECONDS)).fetchone()[0]
                if used >= limit:
                    _insert(conn, tool, profile, recipients, subject, detail, None,
                            "refused_cap", 0)
                    conn.execute("COMMIT")
                    raise Refusal(
                        RATE_LIMITED,
                        f"At most {limit} per hour for this tool, for the whole Maily "
                        "installation, and that many were already used in the last hour. "
                        "Nothing was done; try again later.",
                        "refused_cap")
                row = _insert(conn, tool, profile, recipients, subject, detail, None,
                              "pending", 1)
                conn.execute("COMMIT")
                return row
            except BaseException:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise
    except Refusal:
        raise
    except (sqlite3.Error, OSError) as e:
        log.warning("MCP guard journal unavailable: %s", e)
        raise Refusal(GUARD_UNAVAILABLE,
                      "Maily could not open its safety journal (mcp_guard.sqlite in the "
                      "data folder), so it did nothing. Check the permissions of that folder.",
                      "error") from e


def settle(row: int, decision: str, counted: bool, approval: str | None = None) -> None:
    """Records how a reserved attempt ended. `counted` stays true only when the
    action was started (an attempt that failed in the middle still uses its
    slot: a loop on a failing call must not go on for ever). Never raises: a
    row left "pending" keeps counting, which is the safe side."""
    try:
        with _journal() as conn:
            conn.execute(
                "UPDATE mcp_guard_log SET decision = ?, counted = ?,"
                " approval = COALESCE(?, approval) WHERE id = ?",
                (decision, 1 if counted else 0, approval, row))
    except Exception:
        log.warning("could not update the MCP guard journal", exc_info=True)


def forget_profile(email: str | None) -> int:
    """Erases the journal lines of a profile (called when the account is
    disconnected). Returns the number of lines erased; does nothing, and does
    not create the file, when there is no journal."""
    if not email:
        return 0
    with _journal(create=False) as conn:
        if conn is None:
            return 0
        cur = conn.execute("DELETE FROM mcp_guard_log WHERE lower(profile) = lower(?)",
                           (email,))
        return cur.rowcount


# --- Limits on one message ----------------------------------------------------

class UnreadableRecipients(ValueError):
    """The recipient fields cannot be read the way the sending code will read
    them: the guard does not guess, nothing is sent."""


def parse_recipients(to, cc=None) -> list[tuple[str, str]]:
    """The addresses `to` and `cc` give once read by the parser that builds the
    message (core/mime.py: `EmailMessage`, default policy), as (display name,
    addr_spec) pairs, `to` first. Counting and showing use this list, so what
    the guard counts and what the human reads is what goes out.

    Fails closed: raises UnreadableRecipients when a non-blank field yields no
    address, when the parser raises, or when it reports a defect in the header
    (a lenient reading is exactly where two parsers part ways)."""
    out: list[tuple[str, str]] = []
    for name, value in (("To", to), ("Cc", cc)):
        if value is None or value == "":
            if name == "To":
                raise UnreadableRecipients("`to` is empty")
            continue
        if not isinstance(value, str):
            raise UnreadableRecipients(f"`{name.lower()}` is not text")
        msg = EmailMessage()
        try:
            msg[name] = value
            header = msg[name]
            defects = tuple(getattr(header, "defects", ()) or ())
            found = [(a.display_name or "", a.addr_spec) for a in header.addresses]
        except Exception as e:
            raise UnreadableRecipients(
                f"`{name.lower()}` could not be read as a list of addresses") from e
        if defects:
            raise UnreadableRecipients(
                f"`{name.lower()}` is not a clean list of addresses: write plain "
                "addresses separated by commas")
        if not found or any(not addr or "@" not in addr for _n, addr in found):
            raise UnreadableRecipients(
                f"`{name.lower()}` does not give a readable address")
        out.extend(found)
    return out


def count_recipients(to, cc=None) -> int:
    """Number of addresses in `to` and `cc` (duplicates included), read by the
    same parser as the sending code. Raises UnreadableRecipients."""
    return len(parse_recipients(to, cc))


def check_recipients(to, cc=None) -> int:
    try:
        n = count_recipients(to, cc)
    except UnreadableRecipients as e:
        raise Refusal(TOO_MANY_RECIPIENTS,
                      f"Maily cannot read the recipients reliably ({e}). Nothing was sent.",
                      "refused_cap") from e
    if n > MAX_RECIPIENTS:
        raise Refusal(TOO_MANY_RECIPIENTS,
                      f"{n} recipients in `to` and `cc`; Maily sends to {MAX_RECIPIENTS} "
                      "at most in one message from an MCP client. Nothing was sent.",
                      "refused_cap")
    return n


# --- The human's agreement ----------------------------------------------------

def supports_form_elicitation(ctx) -> bool:
    """True when the client declared elicitation in form mode: an empty
    `elicitation` object counts as form (MCP 2025-11-25), and so does
    `elicitation.form`. A client that only declares `url` cannot show a box:
    treated as having no elicitation. (The SDK's `check_client_capability` only
    tests that `elicitation` is present, which would accept `url` alone.)"""
    try:
        caps = ctx.session.client_params.capabilities.elicitation
    except AttributeError:
        return False
    if caps is None:
        return False
    # Older SDKs have no `form` / `url` fields: an object without them is an
    # empty `elicitation`, which counts as form.
    return getattr(caps, "form", None) is not None or getattr(caps, "url", None) is None


def env_allows(tool: str) -> bool:
    return os.environ.get(ENV_ALLOW[tool], "").strip() == "1"


# Characters that could redraw or hide parts of the box shown to the human:
# controls (but not the newline), bidirectional overrides and isolates, and the
# other format characters.
def _plain(text, limit: int, keep_newlines: bool = False) -> str:
    out = []
    for ch in str(text if text is not None else ""):
        if ch == "\n" and keep_newlines:
            out.append(ch)
        elif unicodedata.category(ch) in ("Cc", "Cf", "Zl", "Zp"):
            out.append(" ")
        else:
            out.append(ch)
    s = "".join(out).strip()
    return s if len(s) <= limit else s[:limit] + "..."


BODY_SHOWN = 4000


def _squeeze_blank_lines(text: str) -> str:
    """Runs of blank lines (spaces or tabs only) become one blank line, so a
    long stretch of empty lines cannot push text out of the box."""
    return re.sub(r"(?:[ \t]*\n){3,}", "\n\n", text)


def _addresses_shown(to, cc) -> tuple[str, str | None]:
    """The To and Cc lines of the box: the addresses as they will go out
    (never the raw string), the display name after the address and short."""
    def show(value):
        if not value:
            return None
        items = []
        for name, addr in parse_recipients(value):
            label = _plain(addr, 320)
            name = _plain(name, 40)
            # A name that looks like an address or breaks out of the brackets
            # could stage a second address in the box: it is left out.
            if name and not any(c in name for c in '@<>,()"'):
                items.append(f"{label} ({name})")
            else:
                items.append(label)
        return ", ".join(items)
    return show(to) or "", show(cc)


def describe_send(profile, to, cc, subject, body_text) -> str:
    """The text of the confirmation box. Raises UnreadableRecipients when the
    recipients cannot be read (callers refuse before asking)."""
    to_line, cc_line = _addresses_shown(to, cc)
    lines = ["Send this email?", "", f"From: {_plain(profile, 200)}", f"To: {to_line}"]
    if cc_line:
        lines.append(f"Cc: {cc_line}")
    body = _squeeze_blank_lines(_plain(body_text, 10 ** 9, keep_newlines=True))
    hidden = len(body) - BODY_SHOWN
    shown = body[:BODY_SHOWN]
    if hidden > 0:
        shown += f"\n\n(+{hidden} characters not shown)"
    lines += [f"Subject: {_plain(subject, 300)}", "", shown]
    return "\n".join(lines)


def describe_trash(profile, sender, subject, date) -> str:
    return "\n".join(["Move this message to the trash?", "",
                      f"Profile: {_plain(profile, 200)}",
                      f"From: {_plain(sender, 300)}",
                      f"Subject: {_plain(subject, 300)}",
                      f"Date: {_plain(date, 40)}"])


def _confirm_model():
    from pydantic import BaseModel, Field

    class Confirm(BaseModel):
        confirm: bool = Field(default=False,
                              description="Tick to allow this action, then accept.")

    return Confirm


async def _ask(ctx, message: str) -> str:
    """Asks the human through the client. Returns "elicitation" on an explicit
    accept with the box ticked; raises Refusal otherwise."""
    try:
        result = await asyncio.wait_for(ctx.elicit(message, _confirm_model()), CONFIRM_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        raise Refusal(CANCELLED, "No answer to the confirmation in time. Nothing was done.",
                      "cancelled")
    except Exception as e:
        log.warning("MCP confirmation failed: %s", type(e).__name__)
        raise Refusal(CONFIRMATION_UNAVAILABLE,
                      "The client could not show or return the confirmation. Nothing was "
                      "done.", "error")
    action = getattr(result, "action", None)
    if action == "accept" and getattr(getattr(result, "data", None), "confirm", False) is True:
        return "elicitation"
    if action == "cancel":
        raise Refusal(CANCELLED, "The confirmation was cancelled. Nothing was done.",
                      "cancelled")
    raise Refusal(DECLINED, "The user did not confirm. Nothing was done.", "declined")


async def authorize(ctx, tool: str, message: str) -> str:
    """Gets the human's agreement. Returns the path taken ("elicitation" or
    "env"); raises Refusal."""
    if supports_form_elicitation(ctx):
        return await _ask(ctx, message)  # never falls back to the variable
    if env_allows(tool):
        return "env"
    var = ENV_ALLOW[tool]
    verb = "send" if tool == "maily_send" else "trash"
    raise Refusal(
        CONFIRMATION_UNAVAILABLE,
        f"This MCP client cannot ask the user for a confirmation (no elicitation), so Maily "
        f"does not {verb}. Nothing was done. To allow it anyway, the owner sets {var}=1 in "
        "the environment of the Maily MCP server (see docs/MCP.md, section 3).",
        "refused_disabled")


# --- The whole guard around one action ---------------------------------------

async def run_guarded(ctx, *, tool: str, profile, recipients, subject, detail,
                      prompt: str, action: Callable[[], object]):
    """Reserves a slot, gets the human's agreement, runs `action`, journals the
    outcome. Raises Refusal when the guard says no; an exception of `action` is
    journalled as "error" (its slot stays used) and raised again."""
    row = reserve(tool, profile, recipients, subject, detail)
    try:
        approval = await authorize(ctx, tool, prompt)
    except Refusal as r:
        settle(row, r.decision, counted=False)
        raise
    except BaseException:
        settle(row, "cancelled", counted=False)
        raise
    settle(row, "pending", counted=True, approval=approval)
    try:
        result = action()
    except BaseException:
        settle(row, "error", counted=True)
        raise
    settle(row, _DONE[tool], counted=True)
    return result
