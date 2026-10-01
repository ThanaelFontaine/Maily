from __future__ import annotations
import os
import sys
import pathlib

APP_NAME = "Maily"
_SLUG = "maily"

# Environment variable that replaces the default data folder. Used by the
# tests, the screenshots and anyone who wants a separate database
# (e.g. MAILY_DATA_DIR=/tmp/maily-demo uv run maily).
DATA_DIR_ENV = "MAILY_DATA_DIR"


def runtime_dir(override: str | None = None) -> pathlib.Path:
    """Folder of the local data (database, attachments, encrypted secrets).

    Priority: the `override` argument, then the MAILY_DATA_DIR variable, then
    the standard folder of the platform.
    """
    if override:
        return pathlib.Path(override).expanduser()
    env = os.environ.get(DATA_DIR_ENV, "").strip()
    if env:
        return pathlib.Path(env).expanduser()
    home = pathlib.Path(os.environ.get("HOME", os.path.expanduser("~")))
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / APP_NAME
    if os.name == "nt":
        base = os.environ.get("APPDATA") or str(home / "AppData" / "Roaming")
        return pathlib.Path(base) / APP_NAME
    xdg = os.environ.get("XDG_DATA_HOME")
    base = pathlib.Path(xdg) if xdg else home / ".local" / "share"
    return base / _SLUG


def ensure_runtime_dirs(base: pathlib.Path) -> dict[str, pathlib.Path]:
    base = pathlib.Path(base)
    attachments = base / "attachments"
    logs = base / "logs"
    for d in (base, attachments, logs):
        d.mkdir(parents=True, exist_ok=True)
        if os.name == "posix":
            os.chmod(d, 0o700)
    return {
        "base": base,
        "db": base / "app.sqlite",
        "attachments": attachments,
        "logs": logs,
        "runtime_json": base / "runtime.json",
    }
