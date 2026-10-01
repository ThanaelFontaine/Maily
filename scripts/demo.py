#!/usr/bin/env python3
"""Demo mode: the Maily interface on fictitious data.

Used to try the interface, to develop the frontend and to take the
screenshots, WITHOUT a Google account, without network and without ever
touching the real data folder or the real secrets:

- the database is created in a temporary folder (or the one given with
  --data-dir, which must be different from Maily's standard folder);
- the local API token is generated in memory, nothing is written to
  secrets.enc;
- sending and syncing are disabled; read/unread, archive and trash only apply
  to the demo database.

Usage (from the repository root):
  uv run python scripts/demo.py                    # temporary folder, free port
  uv run python scripts/demo.py --port 8765 --data-dir /tmp/maily-demo

Then open the printed URL in a browser. Ctrl+C to stop.
"""
from __future__ import annotations
import argparse
import json
import os
import pathlib
import secrets
import sys
import tempfile
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from core import paths  # noqa: E402

_NOW_MS = int(time.time() * 1000)
_HOUR = 3600 * 1000
_DAY = 24 * _HOUR

ACCOUNTS = [
    {"email": "alex@example.com", "display_name": "Personal", "color": "#1a73e8", "provider": "gmail"},
    {"email": "alex.martin@example.org", "display_name": "Work", "color": "#188038", "provider": "gmail"},
    {"email": "alex@example.net", "display_name": "Old address", "color": "#e37400", "provider": "imap"},
]

LABELS = [
    {"id": "INBOX", "name": "INBOX", "type": "system"},
    {"id": "Label_1", "name": "Invoices", "type": "user"},
    {"id": "Label_2", "name": "Travel", "type": "user"},
]

_SIGNATURE = "<p style=\"color:#5e6368\">Camille<br>Project team</p>"

MESSAGES = [
    # (account, sender, subject, snippet, html, age, labels, unread, attachment)
    (0, "Camille Durand <camille@example.com>", "Thursday's progress meeting",
     "Here are the minutes of the meeting and the next steps.",
     "<p>Hi Alex,</p><p>Here are the minutes of our Thursday meeting:</p>"
     "<ul><li>the home page mockup is approved;</li>"
     "<li>the launch is planned for the end of the month;</li>"
     "<li>the FAQ texts still need a review.</li></ul>"
     "<p>The full document is attached. Have a nice day!</p>" + _SIGNATURE,
     1 * _HOUR, ["INBOX", "UNREAD"], True, True),
    (0, "The Sunday Letter <letter@news.example.com>", "Five autumn walks to try",
     "Forests, coasts and villages: our pick of the week.",
     "<p><img src=\"https://news.example.com/banner.png\" alt=\"Banner\" width=\"600\"></p>"
     "<h2>Five autumn walks to try</h2>"
     "<p>Forests, coasts and villages: our pick of the week, with maps and walking times.</p>"
     "<p><img src=\"https://news.example.com/pixel.gif\" width=\"1\" height=\"1\" alt=\"\"></p>",
     3 * _HOUR, ["INBOX", "UNREAD", "CATEGORY_PROMOTIONS"], True, False),
    (0, "Example Bank <no-reply@bank.example.com>", "Your September statement is available",
     "Your account statement is available in your customer area.",
     "<p>Hello,</p><p>Your September account statement is available in your customer area.</p>"
     "<p>This is an automatic message, please do not reply.</p>",
     20 * _HOUR, ["INBOX", "CATEGORY_UPDATES", "Label_1"], False, False),
    (0, "Jordan Petit <jordan@example.org>", "Weekend photos",
     "Here is the link to the album, tell me if you can open it.",
     "<p>Hi!</p><p>Here is the link to the weekend album. Tell me if you can open it.</p><p>Jordan</p>",
     2 * _DAY, ["INBOX"], False, False),
    (0, "Example Rail <tickets@rail.example.com>", "Your ticket to Lyon",
     "Departure 8:12, coach 14, seat 62.",
     "<p>Your ticket is confirmed.</p><table cellpadding=\"6\"><tr><td><b>Departure</b></td><td>8:12</td></tr>"
     "<tr><td><b>Coach</b></td><td>14</td></tr><tr><td><b>Seat</b></td><td>62</td></tr></table>",
     4 * _DAY, ["INBOX", "CATEGORY_UPDATES", "Label_2"], False, True),
    (0, "Social Network <notification@social.example.com>", "You have 3 new notifications",
     "Sam and 2 other people reacted to your post.",
     "<p>Sam and 2 other people reacted to your post.</p>",
     5 * _DAY, ["INBOX", "CATEGORY_SOCIAL"], True, False),
    (1, "Morgan Leroy <morgan@example.org>", "Contract review",
     "I added my remarks as comments, nothing blocking.",
     "<p>Hi Alex,</p><p>I added my remarks as comments in the document, nothing blocking.</p>"
     "<p>Shall we talk about it tomorrow?</p><p>Morgan</p>",
     5 * _HOUR, ["INBOX", "UNREAD"], True, False),
    (1, "Ticket tool <support@tickets.example.org>", "[#4821] Login issue solved",
     "The ticket was closed by the support team.",
     "<p>Ticket <b>#4821</b> was closed by the support team.</p>",
     1 * _DAY, ["INBOX", "CATEGORY_UPDATES"], False, False),
    (2, "Example Association <contact@asso.example.net>", "General meeting on October 12",
     "Agenda and proxy form.",
     "<p>Dear members,</p><p>The general meeting will take place on October 12 at 6 pm. The agenda is below.</p>",
     3 * _DAY, ["INBOX", "UNREAD"], True, False),
]


def seed(store) -> None:
    ids = [store.upsert_account(a["email"], display_name=a["display_name"], color=a["color"],
                                provider=a["provider"]) for a in ACCOUNTS]
    for aid in ids[:2]:
        store.replace_labels(aid, LABELS)
    for n, (acc, frm, subject, snippet, html, age, labels, unread, att) in enumerate(MESSAGES):
        aid = ids[acc]
        mid = store.upsert_message(
            aid, f"demo-{n}", thread_id=f"t-{n}", addr_from=frm, addr_to=ACCOUNTS[acc]["email"],
            subject=subject, snippet=snippet, body_html=html,
            body_text=snippet, internal_date=_NOW_MS - age, label_ids=json.dumps(labels),
            is_unread=1 if unread else 0, has_attachments=1 if att else 0)
        if att:
            store.replace_attachments(mid, [{"filename": "meeting-minutes.pdf" if n == 0 else "ticket.pdf",
                                             "mime_type": "application/pdf", "size": 48213,
                                             "gmail_attachment_id": f"att-{n}"}])


def _default_data_dir() -> pathlib.Path:
    saved = os.environ.pop(paths.DATA_DIR_ENV, None)
    try:
        return paths.runtime_dir().resolve()
    finally:
        if saved is not None:
            os.environ[paths.DATA_DIR_ENV] = saved


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="The Maily interface on fictitious data.")
    ap.add_argument("--data-dir", help="folder of the demo database (default: a temporary folder)")
    ap.add_argument("--port", type=int, default=0, help="local port (default: a free port)")
    args = ap.parse_args(argv)

    data_dir = pathlib.Path(args.data_dir).expanduser() if args.data_dir else \
        pathlib.Path(tempfile.mkdtemp(prefix="maily-demo-"))
    real = _default_data_dir()
    target = data_dir.resolve()
    if target == real or real in target.parents:
        raise SystemExit("Refused: --data-dir points to Maily's real data folder (or one of its "
                         "subfolders). Choose another folder.")
    os.environ[paths.DATA_DIR_ENV] = str(data_dir)

    import uvicorn
    from api.app import create_app
    from app.bootstrap import _frontend_dir, free_port
    from core.db import Database
    from core.store import Store

    layout = paths.ensure_runtime_dirs(data_dir)
    store = Store(Database(layout["db"]))
    if not store.list_accounts():
        seed(store)

    def act_fn(message_id, action, add=None, remove=None):
        if action == "modify":
            store.apply_local_labels(message_id, add=add, remove=remove)
        elif action in ("trash", "untrash"):
            store.set_trashed(message_id, action == "trash")
        return {"ok": True}

    def send_fn(payload):
        raise RuntimeError("sending is disabled in demo mode")

    def download_fn(message_id, att_id):
        att = store.get_attachment(att_id)
        return b"%PDF-1.4\n% demo file\n", "application/pdf", att["filename"]

    token = secrets.token_urlsafe(24)   # in memory only, never written to disk
    app = create_app(store, token, sync_fn=lambda account_id: 0, send_fn=send_fn, act_fn=act_fn,
                     download_fn=download_fn, frontend_dir=_frontend_dir())
    port = args.port or free_port()
    print(f"Maily (demo): http://127.0.0.1:{port}/")
    print(f"Fictitious data in: {data_dir}")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
