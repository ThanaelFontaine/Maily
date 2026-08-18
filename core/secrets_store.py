from __future__ import annotations
import json
import keyring

SERVICE = "Maily"
_CLIENT_KEY = "oauth_client"


def save_client_config(client_id: str, client_secret: str) -> None:
    keyring.set_password(
        SERVICE, _CLIENT_KEY,
        json.dumps({"client_id": client_id, "client_secret": client_secret}),
    )


def load_client_config() -> dict | None:
    raw = keyring.get_password(SERVICE, _CLIENT_KEY)
    return json.loads(raw) if raw else None


def _account_key(email: str) -> str:
    return f"account:{email}"


def save_account_token(email: str, token: dict) -> None:
    keyring.set_password(SERVICE, _account_key(email), json.dumps(token))


def load_account_token(email: str) -> dict | None:
    raw = keyring.get_password(SERVICE, _account_key(email))
    return json.loads(raw) if raw else None


def delete_account_token(email: str) -> None:
    keyring.delete_password(SERVICE, _account_key(email))
