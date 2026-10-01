#!/usr/bin/env python3
"""Stores the OAuth client (client_id/secret) in the encrypted store, without ever printing the secret.

Usage:
  uv run python scripts/store_client_config.py /path/to/client_secret_xxx.json
  uv run python scripts/store_client_config.py        # interactive mode (hidden input)

The client_secret is never printed nor logged. It is written only to
secrets.enc (encrypted, 0600) in Maily's data folder.
"""
from __future__ import annotations
import json
import sys
import getpass
import pathlib

# Make the script runnable directly (adds the project root to the path).
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from core import secrets_store


def from_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    node = data.get("installed") or data.get("web") or data
    cid = node.get("client_id")
    secret = node.get("client_secret")
    if not cid or not secret:
        sys.exit("Invalid JSON: client_id/client_secret not found "
                 "(an OAuth client of type 'Desktop app' is expected).")
    return cid, secret


def interactive():
    cid = input("Client ID: ").strip()
    secret = getpass.getpass("Client secret (hidden input, nothing is shown): ").strip()
    if not cid or not secret:
        sys.exit("Empty client_id/client_secret.")
    return cid, secret


def main():
    if len(sys.argv) > 1:
        cid, secret = from_json(sys.argv[1])
    else:
        cid, secret = interactive()
    secrets_store.save_client_config(cid, secret)
    tail = cid[-16:] if len(cid) > 16 else cid
    print(f"OK: client credentials stored in the encrypted store (client_id ...{tail}).")
    print("The client_secret was never printed.")


if __name__ == "__main__":
    main()
