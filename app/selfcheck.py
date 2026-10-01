"""Self-check of a built Maily (used by the CI on every packaged binary).

`Maily --self-check` checks, without a window and without touching the real
data folder, that the pieces a frozen binary tends to lose are there: the
embedded frontend and migrations, a database created from the migrations,
the encryption of the secret store, the TLS CA bundle, the local API and the
native window library.

`Maily --self-check --window` also opens a real window on the local API (a
throwaway database in a temporary folder, no account, no network) and checks
that the interface page loads, then closes it. It needs a display (on a
headless Linux runner: `xvfb-run`).

`--report FILE` also writes the result to FILE: a windowed binary has no
standard output on Windows. The exit code is 0 when every check passed.
"""
from __future__ import annotations

import os
import pathlib
import sys
import tempfile
import threading
import time
import traceback

WINDOW_TIMEOUT_SECONDS = 90


def _checks(data_dir: pathlib.Path) -> list[tuple[str, object]]:
    """Returns (name, function) pairs; each function returns a short detail."""

    def version():
        import core
        return core.__version__

    def frontend():
        from app import bootstrap
        index = bootstrap._frontend_dir() / "index.html"
        if not index.is_file():
            raise FileNotFoundError(index)
        return str(index.parent)

    def database():
        from core import db
        files = sorted(p.name for p in db.migrations_dir().glob("*.sql"))
        if not files:
            raise FileNotFoundError(db.migrations_dir())
        conn = db.connect(data_dir / "selfcheck.sqlite")
        try:
            level = db.apply_migrations(conn)
        finally:
            conn.close()
        return f"{len(files)} migrations, schema {level}"

    def encryption():
        from cryptography.fernet import Fernet
        f = Fernet(Fernet.generate_key())
        if f.decrypt(f.encrypt(b"maily")) != b"maily":
            raise ValueError("Fernet round trip failed")
        return "Fernet OK"

    def tls_bundle():
        import certifi
        where = certifi.where()
        if not os.path.isfile(where):
            raise FileNotFoundError(where)
        return where

    def local_api():
        import anyio._backends._asyncio  # noqa: F401  (loaded dynamically by anyio)
        import uvicorn  # noqa: F401
        from api.app import create_app  # noqa: F401
        return "FastAPI, uvicorn, anyio"

    def window_library():
        import webview  # noqa: F401
        return "pywebview imported"

    return [("version", version), ("frontend", frontend), ("database", database),
            ("encryption", encryption), ("tls bundle", tls_bundle),
            ("local api", local_api), ("window library", window_library)]


def _window_check(data_dir: pathlib.Path) -> str:
    """Opens a real window on the local API and waits for the page to load."""
    import secrets
    import webview
    from app import bootstrap
    from core.db import Database
    from core.store import Store
    from api.app import create_app

    store = Store(Database(data_dir / "window.sqlite"))
    app = create_app(store, secrets.token_urlsafe(16), frontend_dir=bootstrap._frontend_dir())
    port = bootstrap.free_port()
    bootstrap._start_server(app, port)
    base = f"http://127.0.0.1:{port}"
    if not bootstrap.wait_for_health(base):
        raise RuntimeError("the local server did not start")

    result: dict = {}
    win = webview.create_window("Maily self-check", base, width=800, height=600)

    def on_loaded():
        try:
            result["title"] = win.evaluate_js("document.title")
        except Exception as e:  # noqa: BLE001
            result["error"] = f"{type(e).__name__}: {e}"
        finally:
            win.destroy()

    def watchdog():
        time.sleep(WINDOW_TIMEOUT_SECONDS)
        if "title" not in result and "error" not in result:
            result["error"] = f"the page did not load within {WINDOW_TIMEOUT_SECONDS} s"
            try:
                win.destroy()
            except Exception:  # noqa: BLE001
                pass

    win.events.loaded += on_loaded
    threading.Thread(target=watchdog, daemon=True).start()
    webview.start(private_mode=True)
    if "error" in result:
        raise RuntimeError(result["error"])
    if result.get("title") != "Maily":
        raise RuntimeError(f"unexpected page title {result.get('title')!r}")
    backend = getattr(getattr(webview, "guilib", None), "__name__", "?").rsplit(".", 1)[-1]
    return f"page loaded ({backend} backend)"


def run(argv: list[str]) -> int:
    """Entry point of `Maily --self-check [--window] [--report FILE]`."""
    report_path = None
    if "--report" in argv:
        i = argv.index("--report")
        if i + 1 >= len(argv):
            print("--report needs a file name", file=sys.stderr)
            return 2
        report_path = argv[i + 1]

    lines: list[str] = []
    ok = True
    previous = os.environ.get("MAILY_DATA_DIR")
    with tempfile.TemporaryDirectory(prefix="maily-selfcheck-", ignore_cleanup_errors=True) as tmp:
        data_dir = pathlib.Path(tmp)
        # Never the real data folder, whatever a check imports.
        os.environ["MAILY_DATA_DIR"] = str(data_dir)
        try:
            checks = _checks(data_dir)
            if "--window" in argv:
                checks.append(("window", lambda: _window_check(data_dir)))
            for name, fn in checks:
                try:
                    lines.append(f"ok   {name}: {fn()}")
                except Exception as e:  # noqa: BLE001
                    ok = False
                    lines.append(f"FAIL {name}: {type(e).__name__}: {e}")
                    lines.extend("     " + ln for ln in traceback.format_exc().splitlines())
        finally:
            if previous is None:
                os.environ.pop("MAILY_DATA_DIR", None)
            else:
                os.environ["MAILY_DATA_DIR"] = previous
    lines.append("Self-check passed." if ok else "Self-check FAILED.")
    text = "\n".join(lines) + "\n"
    if sys.stdout is not None:
        sys.stdout.write(text)
        sys.stdout.flush()
    if report_path:
        pathlib.Path(report_path).write_text(text, encoding="utf-8")
    return 0 if ok else 1
