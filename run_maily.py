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


def _ensure_std_streams() -> None:
    """Gives a windowed binary real standard streams.

    A windowed PyInstaller program on Windows starts with sys.stdout and
    sys.stderr set to None; uvicorn's log formatter calls sys.stdout.isatty()
    and the local server would fail to start. They are pointed to the null
    device instead (the logs go to <data>/logs/maily.log anyway).
    """
    import os
    for name in ("stdout", "stderr"):
        if getattr(sys, name) is None:
            setattr(sys, name, open(os.devnull, "w", encoding="utf-8"))


def main() -> None:
    _ensure_std_streams()
    if len(sys.argv) > 1 and sys.argv[1] == "--tls-selftest":
        raise SystemExit(_tls_selftest())
    if len(sys.argv) > 1 and sys.argv[1] == "--version":
        import core
        print(f"Maily {core.__version__}")
        raise SystemExit(0)
    if len(sys.argv) > 1 and sys.argv[1] == "--self-check":
        # Checks a built binary (see app/selfcheck.py); used by the CI.
        from app import selfcheck
        raise SystemExit(selfcheck.run(sys.argv[2:]))
    from app.bootstrap import run
    run()


if __name__ == "__main__":
    multiprocessing.freeze_support()  # needed on Windows in a frozen binary
    main()
