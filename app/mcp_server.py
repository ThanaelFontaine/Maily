"""Local "Maily" MCP server: exposes Maily's multi-profile mailboxes as tools
for an MCP client running on the same machine (Claude Code, Claude Desktop, or
any other stdio MCP client).

It imports the Maily engine directly (same local SQLite database, same
encrypted secrets in the data folder, see core/paths.py and MAILY_DATA_DIR).
No network, no port: stdio transport. Reading the secrets does NOT ask for
Touch ID (the biometric gate only protects the launch of the desktop app): this
is on purpose, so that local automations work without friction. See
docs/MCP.md.

Launch (command to declare in the MCP configuration of the client):
    uv --directory <path-to-the-repository> run python -m app.mcp_server
"""
from __future__ import annotations
import datetime
import re
from html.parser import HTMLParser
from mcp.server.fastmcp import FastMCP
from core import paths
from core.db import Database
from core.store import Store

mcp = FastMCP("Maily")

_store: Store | None = None

_CATEGORY_LABELS = {
    "promotions": "CATEGORY_PROMOTIONS",
    "social": "CATEGORY_SOCIAL",
    "updates": "CATEGORY_UPDATES",
    "forums": "CATEGORY_FORUMS",
}


def store() -> Store:
    global _store
    if _store is None:
        layout = paths.ensure_runtime_dirs(paths.runtime_dir())
        _store = Store(Database(layout["db"]))
    return _store


def _resolve_account(profile) -> dict | None:
    """Accepts an id (int), an email address, or a profile name (display_name),
    case-insensitive. Returns the account (dict) or None."""
    if profile is None:
        return None
    accounts = [dict(a) for a in store().list_accounts()]
    # numeric id
    try:
        pid = int(profile)
        for a in accounts:
            if a["id"] == pid:
                return a
    except (TypeError, ValueError):
        pass
    key = str(profile).strip().lower()
    for a in accounts:
        if (a.get("email") or "").lower() == key:
            return a
    for a in accounts:
        if (a.get("display_name") or "").lower() == key:
            return a
    # partial match on the address as a last resort
    for a in accounts:
        if key and key in (a.get("email") or "").lower():
            return a
    return None


class _TextExtractor(HTMLParser):
    _SKIP = {"script", "style", "head", "title"}

    def __init__(self):
        super().__init__()
        self._parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in self._SKIP:
            self._skip += 1
        elif tag in ("br", "p", "div", "tr", "li", "h1", "h2", "h3"):
            self._parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self._SKIP and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip and data.strip():
            self._parts.append(data)

    # Invisible characters often found in marketing preheaders.
    _INVISIBLE = re.compile(
        "[\u00ad\u200b-\u200f\u202a-\u202e\u2060-\u2063\ufeff]")

    def text(self) -> str:
        raw = "".join(self._parts)
        raw = self._INVISIBLE.sub("", raw)
        raw = re.sub(r"[ \t]+", " ", raw)
        raw = re.sub(r" *\n *", "\n", raw)
        return re.sub(r"\n{3,}", "\n\n", raw).strip()


def _html_to_text(html: str) -> str:
    p = _TextExtractor()
    try:
        p.feed(html or "")
    except Exception:
        return ""
    return p.text()


def _iso(ms) -> str | None:
    if not ms:
        return None
    try:
        return datetime.datetime.fromtimestamp(int(ms) / 1000).isoformat(timespec="seconds")
    except Exception:
        return None


def _msg_brief(row) -> dict:
    m = dict(row)
    return {
        "id": m["id"],
        "account_id": m["account_id"],
        "date": _iso(m.get("internal_date")),
        "from": m.get("addr_from"),
        "to": m.get("addr_to"),
        "subject": m.get("subject"),
        "snippet": m.get("snippet"),
        "unread": bool(m.get("is_unread")),
        "has_attachments": bool(m.get("has_attachments")),
    }


@mcp.tool()
def maily_list_accounts() -> list[dict]:
    """Lists the email profiles available in Maily (id, email, name, color).
    Use the email or the name as the `profile` parameter of the other tools."""
    return [
        {"id": a["id"], "email": a["email"], "name": a["display_name"], "color": a["color"]}
        for a in (dict(x) for x in store().list_accounts())
    ]


@mcp.tool()
def maily_list_messages(profile: str, category: str = "inbox",
                        limit: int = 20, unread_only: bool = False) -> dict:
    """Lists the recent messages of a profile.

    profile   : email or name of the profile (e.g. 'alex@example.com' or 'Personal').
    category  : 'inbox' | 'primary' | 'promotions' | 'social' | 'updates' | 'forums' | 'archived' | 'all'.
    limit     : maximum number (default 20).
    unread_only : keep unread messages only.
    """
    acc = _resolve_account(profile)
    if not acc:
        return {"error": f"profile not found: {profile!r}",
                "known": [a["email"] for a in (dict(x) for x in store().list_accounts())]}
    require, exclude = [], []
    cat = (category or "inbox").lower()
    if cat == "all":
        pass
    elif cat == "archived":
        exclude.append("INBOX")
    elif cat in _CATEGORY_LABELS:
        require += ["INBOX", _CATEGORY_LABELS[cat]]
    elif cat == "primary":
        require.append("INBOX")
        exclude += list(_CATEGORY_LABELS.values())
    else:  # inbox
        require.append("INBOX")
    rows = store().list_messages(acc["id"], require_labels=require, exclude_labels=exclude,
                                 trashed=False, limit=max(1, min(limit, 100)), offset=0)
    msgs = [_msg_brief(r) for r in rows]
    if unread_only:
        msgs = [m for m in msgs if m["unread"]]
    return {"profile": acc["email"], "category": cat, "count": len(msgs), "messages": msgs}


@mcp.tool()
def maily_get_message(message_id: int, include_html: bool = False) -> dict:
    """Returns the full content of a message (sender, recipients, date,
    subject, text body, attachments with their attachment_id). Set
    `include_html=True` to also get the raw HTML."""
    m = store().get_message(message_id)
    if not m:
        return {"error": f"message {message_id} not found"}
    m = dict(m)
    out = {
        "id": m["id"],
        "account_id": m["account_id"],
        "date": _iso(m.get("internal_date")),
        "from": m.get("addr_from"),
        "to": m.get("addr_to"),
        "cc": m.get("addr_cc"),
        "subject": m.get("subject"),
        "unread": bool(m.get("is_unread")),
        "thread_id": m.get("thread_id"),
    }
    body = (m.get("body_text") or "").strip()
    if not body and m.get("body_html"):
        body = _html_to_text(m["body_html"])
    out["body_text"] = body
    # Attachments (embedded cid: images excluded): ids to pass to
    # maily_download_attachment.
    try:
        atts = [dict(a) for a in store().list_attachments(message_id)]
    except Exception:
        atts = []
    out["attachments"] = [
        {"attachment_id": a["id"], "filename": a.get("filename"),
         "mime_type": a.get("mime_type"), "size": a.get("size")}
        for a in atts if not a.get("content_id")
    ]
    if include_html:
        out["body_html"] = m.get("body_html")
    return out


@mcp.tool()
def maily_search(query: str, profile: str | None = None, limit: int = 20) -> dict:
    """Local full-text search (subject, body, sender). Optional `profile` to
    restrict it to one account; otherwise searches every profile."""
    acc = _resolve_account(profile) if profile else None
    if profile and not acc:
        return {"error": f"profile not found: {profile!r}"}
    rows = store().search_messages(query, account_id=acc["id"] if acc else None,
                                   limit=max(1, min(limit, 100)))
    return {"query": query, "profile": acc["email"] if acc else "all",
            "count": len(rows), "messages": [_msg_brief(r) for r in rows]}


@mcp.tool()
def maily_sync(profile: str | None = None) -> dict:
    """Syncs from the mail server (fetches new messages). Without `profile`,
    syncs every account. Returns the number of changes per profile."""
    from core.accounts_service import sync_account
    from core.config import load_settings
    months = load_settings().backfill_months

    def _one(acc: dict) -> int:
        if not store().get_sync_state(acc["id"], "backfill_done"):
            return sync_account(store(), acc["email"], acc["id"], full=True,
                                query=f"newer_than:{months}m")
        return sync_account(store(), acc["email"], acc["id"])

    if profile:
        acc = _resolve_account(profile)
        if not acc:
            return {"error": f"profile not found: {profile!r}"}
        targets = [acc]
    else:
        targets = [dict(a) for a in store().list_accounts()]

    results = {}
    for acc in targets:
        try:
            results[acc["email"]] = _one(acc)
        except Exception as e:
            results[acc["email"]] = f"error: {e}"
    return {"synced": results}


@mcp.tool()
def maily_send(profile: str, to: str, subject: str, body_text: str,
               cc: str | None = None) -> dict:
    """Sends an email FROM a profile (Gmail accounts only). Irreversible
    action: ask the user for confirmation before calling this tool.

    profile : email or name of the sender profile.
    to      : recipient(s), separated by commas.
    """
    acc = _resolve_account(profile)
    if not acc:
        return {"error": f"profile not found: {profile!r}"}
    from core.accounts_service import send_from_account
    payload = {"account_id": acc["id"], "to": to, "subject": subject,
               "body_text": body_text, "cc": cc, "attachments": []}
    try:
        res = send_from_account(store(), acc["email"], acc["id"], payload)
    except Exception as e:
        return {"error": f"sending failed: {e}"}
    return {"sent_from": acc["email"], "to": to, "result": res}


def _save_path(dest_path, filename):
    import pathlib
    if dest_path:
        p = pathlib.Path(dest_path).expanduser()
        if p.is_dir():
            p = p / filename
    else:
        p = pathlib.Path.home() / "Downloads" / filename
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _account_of(message_id):
    m = store().get_message(message_id)
    if not m:
        return None, None
    m = dict(m)
    acc = store().get_account(m["account_id"])
    return m, (dict(acc) if acc else None)


@mcp.tool()
def maily_export_eml(message_id: int, dest_path: str | None = None) -> dict:
    """Saves a message as an .eml file (raw RFC 822) on disk.
    dest_path : folder or full path (default: ~/Downloads). Works for Gmail
    and IMAP accounts. Returns the path of the written file."""
    from core.accounts_service import export_eml
    try:
        data, filename = export_eml(store(), message_id)
    except Exception as e:
        return {"error": f".eml export failed: {e}"}
    p = _save_path(dest_path, filename)
    p.write_bytes(data)
    return {"saved": str(p), "bytes": len(data)}


@mcp.tool()
def maily_download_attachment(message_id: int, attachment_id: int,
                             dest_path: str | None = None) -> dict:
    """Downloads an attachment of a message to disk.
    dest_path : folder or full path (default: ~/Downloads)."""
    from core.accounts_service import fetch_attachment
    m, acc = _account_of(message_id)
    if not acc:
        return {"error": f"message {message_id} not found"}
    attdir = paths.ensure_runtime_dirs(paths.runtime_dir())["attachments"]
    try:
        data, mime, filename = fetch_attachment(store(), acc["email"], message_id,
                                                attachment_id, attdir)
    except Exception as e:
        return {"error": f"download failed: {e}"}
    p = _save_path(dest_path, filename or "attachment")
    p.write_bytes(data)
    return {"saved": str(p), "mime": mime, "bytes": len(data)}


@mcp.tool()
def maily_trash(message_id: int) -> dict:
    """Moves a message to the trash. Reversible for a Gmail profile; for an
    IMAP profile the message goes to the server's trash folder and Maily
    cannot restore it. Management action: confirm with the user before
    calling this tool."""
    from core.accounts_service import trash_message
    m, acc = _account_of(message_id)
    if not acc:
        return {"error": f"message {message_id} not found"}
    try:
        trash_message(store(), acc["email"], message_id)
    except Exception as e:
        return {"error": f"moving to trash failed: {e}"}
    return {"trashed": message_id, "profile": acc["email"]}


def main():
    mcp.run()


if __name__ == "__main__":
    main()
