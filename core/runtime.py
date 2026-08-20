from __future__ import annotations
import json
import os
import pathlib
import secrets
from core import secret_file

SERVICE = "Maily"
_TOKEN_KEY = "api_token"
SCHEMA_VERSION = "1"


def get_or_create_api_token() -> str:
    tok = secret_file.get(_TOKEN_KEY)
    if not tok:
        tok = secrets.token_urlsafe(32)
        secret_file.set(_TOKEN_KEY, tok)
    return tok


def read_api_token() -> str | None:
    return secret_file.get(_TOKEN_KEY)


def write_runtime_file(path, host: str, port: int, token: str | None = None) -> dict:
    path = pathlib.Path(path)
    data = {
        "host": host,
        "port": port,
        "base_url": f"http://{host}:{port}",
        "schema_version": SCHEMA_VERSION,
    }
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    if os.name == "posix":
        os.chmod(path, 0o600)
    return data


def read_runtime_file(path) -> dict | None:
    path = pathlib.Path(path)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
