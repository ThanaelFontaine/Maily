from __future__ import annotations
import datetime
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google.auth.exceptions import RefreshError
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from core import secrets_store

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.send",
]


class ReauthRequired(Exception):
    pass


def creds_to_dict(creds: Credentials) -> dict:
    return {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes) if creds.scopes else SCOPES,
        "expiry": creds.expiry.isoformat() if getattr(creds, "expiry", None) else None,
    }


def dict_to_creds(d: dict) -> Credentials:
    exp = d.get("expiry")
    expiry = datetime.datetime.fromisoformat(exp) if exp else None
    return Credentials(
        token=d.get("token"),
        refresh_token=d.get("refresh_token"),
        token_uri=d.get("token_uri", "https://oauth2.googleapis.com/token"),
        client_id=d.get("client_id"),
        client_secret=d.get("client_secret"),
        scopes=d.get("scopes", SCOPES),
        expiry=expiry,
    )


def load_credentials(email: str) -> Credentials:
    token = secrets_store.load_account_token(email)
    if not token:
        raise ReauthRequired(f"Aucun token pour {email}")
    creds = dict_to_creds(token)
    if creds.expired or not creds.token:
        try:
            creds.refresh(Request())
        except RefreshError as e:
            raise ReauthRequired(f"Refresh impossible pour {email}: {e}") from e
        secrets_store.save_account_token(email, creds_to_dict(creds))
    return creds


def client_config_dict() -> dict:
    cfg = secrets_store.load_client_config()
    if not cfg:
        raise ReauthRequired("Identifiants client (client_id/secret) absents.")
    return {
        "installed": {
            "client_id": cfg["client_id"],
            "client_secret": cfg["client_secret"],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://127.0.0.1"],
        }
    }


def _fetch_email(creds) -> str:
    service = build("gmail", "v1", credentials=creds, cache_discovery=False)
    profile = service.users().getProfile(userId="me").execute()
    return profile["emailAddress"]


def run_local_auth(open_browser: bool = True) -> str:
    flow = InstalledAppFlow.from_client_config(client_config_dict(), SCOPES)
    creds = flow.run_local_server(host="127.0.0.1", port=0, open_browser=open_browser)
    email = _fetch_email(creds)
    secrets_store.save_account_token(email, creds_to_dict(creds))
    return email
