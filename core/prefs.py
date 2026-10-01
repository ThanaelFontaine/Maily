"""Interface preferences, stored server-side in `prefs.json`.

Why not the webview's localStorage: the local API listens on a random port, so
the page origin (http://127.0.0.1:<port>) changes at every launch and its
localStorage starts empty; on top of that, pywebview ignores `storage_path` on
macOS. The choices (theme, Classic mode, remote images, list width, language)
therefore live in the data folder, like the glass density.

The file is created with mode 0600 and rewritten atomically. Only known keys
are accepted, with validated values: an unexpected value or a damaged file
falls back to the defaults, never to an error at startup.

The Zero Day theme was called `dedsec` before 0.7.0: a stored `dedsec` value is
read as `zeroday` and the file is rewritten once with the new name.
"""
from __future__ import annotations
import json
import os
import tempfile
import threading
from core import paths

_LOCK = threading.RLock()

THEMES = ("classic", "aero", "glass", "zeroday")
# Former theme ids, still accepted and translated to their current id.
THEME_ALIASES = {"dedsec": "zeroday"}
CLASSIC_MODES = ("auto", "light", "dark")
# Interface languages (frontend/i18n/<code>.json). None = follow the system.
LANGUAGES = ("en", "fr", "de", "es", "pt")
LIST_WIDTH_MIN, LIST_WIDTH_MAX = 260, 720

DEFAULTS = {
    "theme": "classic",
    "classic_mode": "auto",
    "remote_images": False,
    "list_width": None,
    "language": None,
}


class InvalidPref(ValueError):
    """Unknown key or invalid value in a preferences update."""


def _path():
    return paths.runtime_dir() / "prefs.json"


def _validate(key, value):
    if key == "theme":
        value = THEME_ALIASES.get(value, value) if isinstance(value, str) else value
        if value not in THEMES:
            raise InvalidPref(f"invalid theme: {value!r}")
        return value
    if key == "classic_mode":
        if value not in CLASSIC_MODES:
            raise InvalidPref(f"invalid classic_mode: {value!r}")
        return value
    if key == "remote_images":
        if not isinstance(value, bool):
            raise InvalidPref("remote_images must be a boolean")
        return value
    if key == "list_width":
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise InvalidPref("list_width must be a number")
        return int(max(LIST_WIDTH_MIN, min(LIST_WIDTH_MAX, value)))
    if key == "language":
        if value is None:
            return None
        if value not in LANGUAGES:
            raise InvalidPref(f"invalid language: {value!r}")
        return value
    raise InvalidPref(f"unknown preference: {key!r}")


def _read_raw():
    """Content of prefs.json as a dict, or None when missing or unreadable."""
    try:
        raw = json.loads(_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return raw if isinstance(raw, dict) else None


def _migrate(raw: dict) -> None:
    """Rewrites former theme ids (dedsec) with their current name, once."""
    theme = raw.get("theme")
    if isinstance(theme, str) and theme in THEME_ALIASES:
        raw["theme"] = THEME_ALIASES[theme]
        try:
            _write(raw)
        except OSError:
            pass


def load() -> dict:
    """Complete preferences (defaults for whatever is missing or invalid)."""
    out = dict(DEFAULTS)
    with _LOCK:
        raw = _read_raw()
        if raw is None:
            return out
        _migrate(raw)
    for key, value in raw.items():
        if key in DEFAULTS:
            try:
                out[key] = _validate(key, value)
            except InvalidPref:
                pass
    return out


def stored_keys() -> set:
    """Keys actually saved (used by the migration from localStorage)."""
    raw = _read_raw()
    return {k for k in raw if k in DEFAULTS} if raw is not None else set()


def _write(data: dict) -> None:
    p = _path()
    if not p.parent.exists():
        p.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if os.name == "posix":
            os.chmod(p.parent, 0o700)
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=".prefs.json.", suffix=".tmp")
    try:
        if os.name == "posix":
            os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            fd = None
            json.dump(data, f, indent=2, sort_keys=True)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, str(p))
        tmp = None
    finally:
        if fd is not None:
            os.close(fd)
        if tmp is not None:
            try:
                os.unlink(tmp)
            except OSError:
                pass


def update(changes: dict) -> dict:
    """Validates then saves `changes` (partial update). Returns the complete preferences.

    Raises InvalidPref without writing anything if a key or a value is invalid.
    """
    if not isinstance(changes, dict):
        raise InvalidPref("a JSON object is expected")
    clean = {k: _validate(k, v) for k, v in changes.items()}
    with _LOCK:
        current = {k: v for k, v in load().items() if k in stored_keys()}
        current.update(clean)
        _write(current)
        return load()
