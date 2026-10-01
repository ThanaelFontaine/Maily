from __future__ import annotations
import json
from core import secret_file

SERVICE = "Maily"
_CLIENT_KEY = "oauth_client"


def save_client_config(client_id: str, client_secret: str) -> None:
    secret_file.set(_CLIENT_KEY, json.dumps({"client_id": client_id, "client_secret": client_secret}))


def load_client_config() -> dict | None:
    raw = secret_file.get(_CLIENT_KEY)
    return json.loads(raw) if raw else None


def _account_key(email: str) -> str:
    return f"account:{email}"


def save_account_token(email: str, token: dict) -> None:
    secret_file.set(_account_key(email), json.dumps(token))


def load_account_token(email: str) -> dict | None:
    raw = secret_file.get(_account_key(email))
    return json.loads(raw) if raw else None


def delete_account_token(email: str) -> None:
    secret_file.delete(_account_key(email))


def _imap_key(email: str) -> str:
    return f"imap:{email}"


def save_imap_credentials(email: str, creds: dict) -> None:
    """creds: {host, port, username, password}. Stored encrypted."""
    secret_file.set(_imap_key(email), json.dumps(creds))


def load_imap_credentials(email: str) -> dict | None:
    raw = secret_file.get(_imap_key(email))
    return json.loads(raw) if raw else None


def delete_imap_credentials(email: str) -> None:
    secret_file.delete(_imap_key(email))
