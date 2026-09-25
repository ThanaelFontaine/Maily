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
    if token is not None:
        data["token"] = token
    # Create file with 0600 permissions atomically (never world-readable).
    # Fix permissions before writing any token bytes (handles pre-existing loose perms).
    # Close fd exactly once on all paths: exception handlers close it if setup fails.
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.fchmod(fd, 0o600)
        f = os.fdopen(fd, "w", encoding="utf-8")
    except BaseException:
        os.close(fd)
        raise
    with f:
        json.dump(data, f, indent=2)
    return data


def read_runtime_file(path) -> dict | None:
    path = pathlib.Path(path)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
