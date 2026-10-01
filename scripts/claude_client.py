#!/usr/bin/env python3
"""Ready-made client for local automations (scripts, agents).

Reads runtime.json (written by the app at launch) and the local API token
(in the encrypted secret store), then talks to Maily's local HTTP API. The
Maily app must be running.

Examples (from the repository root):
  uv run python scripts/claude_client.py accounts
  uv run python scripts/claude_client.py inbox --account 1
  uv run python scripts/claude_client.py read 42
  uv run python scripts/claude_client.py send --account 1 --to dest@example.com --subject "Hello" --body "Hi"

Also importable: `from scripts.claude_client import accounts, messages, read_message, send, sync`.
"""
from __future__ import annotations
import sys
import json
import pathlib
import urllib.request
import urllib.error
import urllib.parse

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from core import paths, runtime


def _base_and_token():
    layout = paths.ensure_runtime_dirs(paths.runtime_dir())
    rt = runtime.read_runtime_file(layout["runtime_json"])
    if not rt:
        raise SystemExit("Maily does not seem to be running (no runtime.json). Start the app first.")
    token = runtime.read_api_token()
    if not token:
        raise SystemExit("API token not found. Start the app at least once.")
    return rt["base_url"], token


def _req(method, path, body=None):
    base, token = _base_and_token()
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Authorization": "Bearer " + token}
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(base + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raise SystemExit(f"API error {e.code} on {path}: {e.read().decode(errors='ignore')}")


def accounts():
    return _req("GET", "/accounts")


def messages(account_id=None, category=None, label=None, trashed=False, archived=False):
    p = []
    if account_id:
        p.append(f"account_id={account_id}")
    if category:
        p.append(f"category={category}")
    if label:
        p.append(f"label={label}")
    if trashed:
        p.append("trashed=true")
    if archived:
        p.append("archived=true")
    return _req("GET", "/messages" + ("?" + "&".join(p) if p else ""))


def read_message(message_id):
    return _req("GET", f"/messages/{message_id}")


def search(q, account_id=None):
    p = "q=" + urllib.parse.quote(q)
    if account_id:
        p += f"&account_id={account_id}"
    return _req("GET", "/search?" + p)


def send(account_id, to, subject, body_text, cc=None, in_reply_to=None, thread_id=None):
    return _req("POST", "/send", {
        "account_id": account_id, "to": to, "subject": subject, "body_text": body_text,
        "cc": cc, "in_reply_to": in_reply_to, "thread_id": thread_id,
    })


def modify(message_id, add_labels=None, remove_labels=None):
    return _req("POST", f"/messages/{message_id}/modify",
                {"add_labels": add_labels or [], "remove_labels": remove_labels or []})


def trash(message_id):
    return _req("POST", f"/messages/{message_id}/trash")


def sync(account_id):
    return _req("POST", f"/accounts/{account_id}/sync")


def _cli():
    import argparse
    import urllib.parse  # noqa: F401 (used by search)
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("accounts")
    p_in = sub.add_parser("inbox"); p_in.add_argument("--account", type=int); p_in.add_argument("--category", default="primary")
    p_rd = sub.add_parser("read"); p_rd.add_argument("id", type=int)
    p_sd = sub.add_parser("send")
    for a in ("--account", "--to", "--subject", "--body"):
        p_sd.add_argument(a, required=True)
    p_sy = sub.add_parser("sync"); p_sy.add_argument("--account", type=int, required=True)
    args = ap.parse_args()

    if args.cmd == "accounts":
        for a in accounts():
            print(a["id"], a["email"], a.get("status", ""))
    elif args.cmd == "inbox":
        for m in messages(account_id=args.account, category=args.category):
            flag = "*" if m["is_unread"] else " "
            print(f'{flag} [{m["id"]}] {(m["addr_from"] or "")[:35]:35} | {(m["subject"] or "")[:50]}')
    elif args.cmd == "read":
        m = read_message(args.id)
        print(f'From: {m["addr_from"]}\nSubject: {m["subject"]}\n\n{m.get("body_text") or "(HTML only)"}')
    elif args.cmd == "send":
        print(send(int(args.account), args.to, args.subject, args.body))
    elif args.cmd == "sync":
        print(sync(args.account))


if __name__ == "__main__":
    import urllib.parse  # for search()
    _cli()
