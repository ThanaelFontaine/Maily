"""Update check: tells the user when a newer Maily release is out.

Free and serverless: it asks the public GitHub API for the latest release
(drafts and prereleases are never "latest") and compares its tag with
`core.__version__`. At most one request per 24 hours, remembered in
`update.json` (data folder, mode 0600). Nothing about the mailboxes is sent;
GitHub only sees the IP address, as for any visit.

Failure is never an error: offline, timeout, HTTP error or unreadable answer
all mean "no update known", and the last remembered answer is kept.
The check is skipped entirely (no network) when the `check_updates` preference
is off, or in demo mode (`offline=True`).
"""
from __future__ import annotations
import datetime
import json
import ssl
import sys
import threading
import urllib.request
from core import paths, prefs

LATEST_URL = "https://api.github.com/repos/ThanaelFontaine/Maily/releases/latest"
TIMEOUT = 6.0
MAX_AGE = datetime.timedelta(hours=24)

_LOCK = threading.Lock()


def _cache_path():
    return paths.runtime_dir() / "update.json"


def parse_version(tag):
    """'v0.9.0' or '0.9.0' as (0, 9, 0); None when it is not plain numeric dotted."""
    if not isinstance(tag, str):
        return None
    parts = tag.strip().removeprefix("v").split(".")
    if not parts or not all(p.isascii() and p.isdigit() for p in parts):
        return None
    return tuple(int(p) for p in parts)


def _tls_context():
    """certifi's CA bundle when available: the packaged app embeds it (packaging/maily.spec),
    while the system's default paths may not exist inside a frozen bundle."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except (ImportError, OSError):
        return ssl.create_default_context()


def fetch_latest():
    """(tag_name, html_url) of the latest release. Raises on any problem."""
    import core
    req = urllib.request.Request(LATEST_URL, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": f"Maily/{core.__version__}",
    })
    with urllib.request.urlopen(req, timeout=TIMEOUT, context=_tls_context()) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["tag_name"], data["html_url"]


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


def _read_cache():
    """Remembered {checked_at, latest, url}, or {} when missing or damaged."""
    try:
        raw = json.loads(_cache_path().read_text(encoding="utf-8"))
        datetime.datetime.fromisoformat(raw["checked_at"])
    except (OSError, ValueError, KeyError, TypeError):
        return {}
    if not isinstance(raw.get("latest"), (str, type(None))):
        return {}
    return raw


def _fresh(cache):
    try:
        age = _now() - datetime.datetime.fromisoformat(cache["checked_at"])
    except (KeyError, ValueError, TypeError):
        return False
    return datetime.timedelta(0) <= age < MAX_AGE


def kind():
    """'app' for the packaged application, 'source' for a checkout run with uv."""
    return "app" if getattr(sys, "frozen", False) else "source"


def _result(enabled, cache, failed=False):
    import core
    latest = cache.get("latest") if enabled else None
    latest_t, current_t = parse_version(latest), parse_version(core.__version__)
    return {
        "enabled": enabled,
        "current": core.__version__,
        "latest": latest,
        "available": bool(latest_t and current_t and latest_t > current_t),
        "kind": kind(),
        "checked_at": cache.get("checked_at") if enabled else None,
        "failed": failed,
    }


def check(force=False, offline=False):
    """State of the update check (see module docstring). Never raises.

    `force` ignores the 24 h memory (the "Check now" button). `failed` is true
    when a request was made and did not give a usable answer.
    """
    enabled = not offline and prefs.load()["check_updates"]
    if not enabled:
        return _result(False, {})
    with _LOCK:
        cache = _read_cache()
        if _fresh(cache) and not force:
            return _result(True, cache)
        try:
            tag, url = fetch_latest()
            version = tag.strip().removeprefix("v") if parse_version(tag) else None
            fresh = {"checked_at": _now().isoformat(timespec="seconds"),
                     "latest": version, "url": url if isinstance(url, str) else None}
        except Exception:
            return _result(True, cache, failed=True)
        try:
            prefs.write_private_json(_cache_path(), fresh)
        except OSError:
            pass                                 # the memory is only an optimisation
        return _result(True, fresh)
