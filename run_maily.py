"""Entry point of the packaged application (PyInstaller)."""
from __future__ import annotations
import multiprocessing
import sys


def _tls_selftest() -> int:
    """Checks that TLS works in the frozen binary (certifi + requests).

    Reproduces exactly the path that failed when adding a Google account
    (OAuth token exchange through requests). Usage: `Maily --tls-selftest`.
    """
    import certifi
    import os
    where = certifi.where()
    print(f"certifi.where() = {where} (exists={os.path.exists(where)})")
    import requests
    try:
        r = requests.get("https://oauth2.googleapis.com/", timeout=8)
        print(f"TLS OK -> HTTP {r.status_code}")
        return 0
    except Exception as e:
        print(f"TLS FAIL -> {type(e).__name__}: {e}")
        return 1


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "--tls-selftest":
        raise SystemExit(_tls_selftest())
    from app.bootstrap import run
    run()


if __name__ == "__main__":
    multiprocessing.freeze_support()  # needed on Windows in a frozen binary
    main()
