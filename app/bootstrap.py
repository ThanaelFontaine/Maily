from __future__ import annotations
import socket
import sys
import threading
import time
import pathlib
import urllib.request


def free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def wait_for_health(base_url, timeout=15.0, interval=0.3, _sleep=time.sleep, _opener=None):
    opener = _opener or urllib.request.urlopen
    attempts = int(timeout / interval) + 1
    for _ in range(attempts):
        try:
            with opener(base_url + "/health", timeout=2) as resp:
                if getattr(resp, "status", 200) == 200:
                    return True
        except Exception:
            pass
        _sleep(interval)
    return False


def make_sync_fn(store, backfill_months=12):
    from core.accounts_service import sync_account

    def _sync(account_id):
        acc = store.get_account(account_id)
        if not acc:
            raise ValueError(f"account {account_id} not found")
        # First sync: bounded backfill (window in months); incremental afterwards.
        if not store.get_sync_state(account_id, "backfill_done"):
            return sync_account(store, acc["email"], account_id,
                                full=True, query=f"newer_than:{backfill_months}m")
        return sync_account(store, acc["email"], account_id)

    return _sync


def make_send_fn(store):
    from core.accounts_service import send_from_account

    def _send(payload):
        acc = store.get_account(payload["account_id"])
        if not acc:
            raise ValueError(f"account {payload['account_id']} not found")
        return send_from_account(store, acc["email"], payload["account_id"], payload)

    return _send


def make_add_google_fn(store, timeout_seconds=180):
    from core.accounts_service import add_google_account

    def _add():
        return add_google_account(store, timeout_seconds=timeout_seconds)

    return _add


def make_add_imap_fn(store):
    from core.accounts_service import add_imap_account

    def _add(email, password, host, port):
        return add_imap_account(store, email, password, host=host, port=port)

    return _add


def make_logout_fn(store):
    from core.accounts_service import logout_account

    def _logout(account_id):
        return logout_account(store, account_id)

    return _logout


def make_eml_fn(store):
    from core.accounts_service import export_eml

    def _eml(message_id):
        return export_eml(store, message_id)

    return _eml


def make_labels_fn(store):
    from core import accounts_service as svc

    def _labels(account_id):
        acc = store.get_account(account_id)
        if not acc:
            raise ValueError(f"account {account_id} not found")
        return svc.refresh_labels(store, acc["email"], account_id)

    return _labels


def make_act_fn(store):
    from core import accounts_service as svc

    def _act(message_id, action, add=None, remove=None):
        m = store.get_message(message_id)
        if not m:
            raise ValueError("message not found")
        acc = store.get_account(m["account_id"])
        email = acc["email"]
        if action == "modify":
            return svc.modify_message(store, email, message_id, add=add, remove=remove)
        if action == "trash":
            return svc.trash_message(store, email, message_id)
        if action == "untrash":
            return svc.untrash_message(store, email, message_id)
        raise ValueError(f"unknown action: {action}")

    return _act


def _migrate_secrets(store) -> None:
    """Moves the Keychain secrets into the encrypted file (once)."""
    from core import secret_file
    names = ["oauth_client", "api_token"]
    try:
        names += [f"account:{a['email']}" for a in store.list_accounts()]
    except Exception:
        pass
    try:
        secret_file.migrate_from_keyring(names)
    except Exception:
        pass


def _frontend_dir() -> pathlib.Path:
    # In a frozen binary (PyInstaller), the frontend is embedded at the root.
    if getattr(sys, "frozen", False):
        return pathlib.Path(getattr(sys, "_MEIPASS", ".")) / "frontend"
    return pathlib.Path(__file__).resolve().parent.parent / "frontend"


def _start_server(app, port):
    import uvicorn

    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    return server


def make_attachment_fns(store, attachments_dir):
    import base64
    from core import accounts_service as svc

    def _email(message_id):
        m = store.get_message(message_id)
        acc = store.get_account(m["account_id"])
        return acc["email"]

    def download_fn(message_id, att_id):
        return svc.fetch_attachment(store, _email(message_id), message_id, att_id, attachments_dir)

    def inline_fn(message_id, att_id):
        data, mime, _filename = svc.fetch_attachment(store, _email(message_id), message_id, att_id, attachments_dir)
        return f"data:{mime or 'application/octet-stream'};base64,{base64.b64encode(data).decode()}"

    return download_fn, inline_fn


# NSVisualEffectView (vibrancy): modern translucent material. Material 0
# (AppearanceBased) is DEPRECATED (10.14) and renders opaque on macOS 26. 21 =
# UnderWindowBackground, designed to show the frosted desktop under a window.
_GLASS_MATERIAL = 21       # NSVisualEffectMaterialUnderWindowBackground
_GLASS_STATE_ACTIVE = 1    # NSVisualEffectStateActive
_GLASS_BLEND_BEHIND = 0    # NSVisualEffectBlendingModeBehindWindow
_GLASS_AUTORESIZE = 18     # NSViewWidthSizable(2) | NSViewHeightSizable(16)

# uids already handled (the re-parenting must happen once per window only).
_GLASS_DONE = set()
# Vibrancy layer of each window, to set its density (alphaValue) from the
# frontend slider. alpha 1 = fully frosted; 0 = sharp desktop.
_GLASS_VEV = {}
_GLASS_ALPHA_DEFAULT = 0.6


def _glass_alpha_path():
    from core import paths
    return paths.runtime_dir() / "glass_alpha"


def get_glass_alpha():
    """Persisted frosted glass density (0..1), 0.6 by default, read at startup."""
    try:
        return max(0.0, min(1.0, float(_glass_alpha_path().read_text().strip())))
    except Exception:
        return _GLASS_ALPHA_DEFAULT


def set_glass_alpha(alpha):
    """Sets the frosted glass density (vibrancy) and persists it; called by the API."""
    try:
        a = max(0.0, min(1.0, float(alpha)))
    except Exception:
        return
    try:  # robust persistence (independent of localStorage / private mode)
        p = _glass_alpha_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(str(a))
    except Exception:
        pass
    try:
        from PyObjCTools import AppHelper
    except Exception:
        return

    def _apply():
        for vev in list(_GLASS_VEV.values()):
            try:
                vev.setAlphaValue_(a)
            except Exception:
                pass

    AppHelper.callAfter(_apply)


def _apply_macos_transparency(win):
    # Reveals the REAL FROSTED (blurred) desktop behind the translucent chrome
    # (Glassmorphism).
    #
    # On macOS 26, two things hid the desktop:
    #   1. The WKWebView painted an opaque underPageBackgroundColor (forced light)
    #      and pywebview's KVC key `drawsTransparentBackground` is deprecated /
    #      a no-op (`drawsBackground` is used instead).
    #   2. pywebview adds the NSVisualEffectView AS A SUBVIEW of the WKWebView
    #      (which IS the contentView). Nested like that, the "behind window"
    #      vibrancy does not composite the desktop (opaque flat color); its
    #      default material (0) is also deprecated.
    # Fix: re-parent, so that contentView = a container holding [vibrancy at the
    # back (material 21), transparent WKWebView in front]. The vibrancy then
    # blurs the desktop and the transparent web content sits on top. Main
    # thread, once.
    #
    # System prerequisite: System Settings > Accessibility > Display > Reduce
    # transparency = OFF (otherwise macOS forces an opaque background).
    if win.uid in _GLASS_DONE:
        return
    try:
        import webview.platforms.cocoa as cocoa
        import AppKit
        from PyObjCTools import AppHelper
    except Exception:
        return
    bv = cocoa.BrowserView.instances.get(win.uid)
    if bv is None:
        return
    _GLASS_DONE.add(win.uid)

    def _set():
        try:
            clear = AppKit.NSColor.clearColor()
            window = bv.window
            webview = bv.webview  # WKWebView (WebKitHost), the contentView

            # 1) A really transparent WKWebView (modern way).
            for setter in (
                lambda: webview.setValue_forKey_(False, "drawsBackground"),
                lambda: webview.setUnderPageBackgroundColor_(clear),
            ):
                try:
                    setter()
                except Exception:
                    pass

            # 2) Gets or creates the vibrancy and gives it a translucent material.
            vev = None
            for sub in list(webview.subviews()):
                if sub.isKindOfClass_(AppKit.NSVisualEffectView):
                    vev = sub
                    break
            if vev is not None:
                vev.removeFromSuperview()
            else:
                vev = AppKit.NSVisualEffectView.new()
            vev.setMaterial_(_GLASS_MATERIAL)
            vev.setBlendingMode_(_GLASS_BLEND_BEHIND)
            vev.setState_(_GLASS_STATE_ACTIVE)

            # 3) New contentView = container; [vibrancy at the back, web in front].
            container = AppKit.NSView.alloc().initWithFrame_(webview.frame())
            container.setAutoresizesSubviews_(True)
            window.setContentView_(container)
            vev.setFrame_(container.bounds())
            vev.setAutoresizingMask_(_GLASS_AUTORESIZE)
            container.addSubview_(vev)
            webview.setFrame_(container.bounds())
            webview.setAutoresizingMask_(_GLASS_AUTORESIZE)
            container.addSubview_positioned_relativeTo_(webview, AppKit.NSWindowAbove, vev)

            # Adjustable frosted density, restored from the persisted value.
            _GLASS_VEV[win.uid] = vev
            vev.setAlphaValue_(get_glass_alpha())

            # 4) Transparent and active window (live recompositing of the desktop).
            window.makeFirstResponder_(webview)
            window.setOpaque_(False)
            window.setBackgroundColor_(clear)
            window.makeKeyAndOrderFront_(None)
            try:
                AppKit.NSApp.activateIgnoringOtherApps_(True)
            except Exception:
                pass
            container.setNeedsDisplay_(True)
        except Exception:
            pass

    AppHelper.callAfter(_set)


def fatal_page(message: str) -> str:
    """Standalone HTML page that explains why Maily cannot start."""
    import html as _html
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'><title>Maily</title>"
        "<style>body{font:14px/1.5 -apple-system,'Segoe UI',system-ui,sans-serif;color:#1f1f1f;"
        "background:#fff;margin:0;padding:28px 32px}h1{font-size:18px;margin:0 0 12px}"
        "p{margin:0 0 10px}code{background:#f1f3f4;padding:1px 4px;border-radius:4px}</style></head><body>"
        "<h1>Maily cannot start</h1>"
        f"<p>{_html.escape(message)}</p>"
        "<p>Nothing was changed. Troubleshooting is explained in the README, section "
        "<code>Troubleshooting</code>.</p></body></html>"
    )


def _show_fatal(message: str) -> None:
    """Shows the error in a window (the packaged app has no terminal)."""
    try:
        import webview
        webview.create_window("Maily", html=fatal_page(message), width=640, height=340)
        webview.start()
    except Exception:
        pass


def fail_unreadable_secrets(error) -> None:
    """Unreadable secret store: message on stderr AND on screen, then exit."""
    message = str(error)
    print(f"Maily cannot start: {message}", file=sys.stderr)
    _show_fatal(message)
    raise SystemExit(2)


def window_kwargs(platform: str, width: int = 1240, height: int = 820) -> dict:
    # Native window transparency per platform:
    # macOS: vibrancy (native frosted blur of the desktop); Linux: transparent
    # (the compositor blurs); elsewhere (Windows): opaque with a light fallback.
    kwargs = {"width": width, "height": height}
    if platform == "darwin":
        kwargs["transparent"] = True
        kwargs["vibrancy"] = True
    elif platform.startswith("linux"):
        kwargs["transparent"] = True
    else:
        kwargs["background_color"] = "#FFFFFF"
    return kwargs


def run():
    import webview
    from core import paths, runtime
    from core.db import Database
    from core.store import Store
    from api.app import create_app

    layout = paths.ensure_runtime_dirs(paths.runtime_dir())
    from core.config import load_settings
    from core.logging_setup import configure_logging
    settings = load_settings()
    # Logs in <data>/logs/maily.log (rotating, secrets redacted).
    configure_logging(layout["logs"], settings.log_level)
    db = Database(layout["db"])
    store = Store(db)

    # Secrets: one-time migration from the Keychain to the local encrypted file
    # (removes the Keychain password prompt in the packaged app), then the
    # Touch ID gate at launch.
    _migrate_secrets(store)
    from core import biometric
    if not biometric.require_unlock("Unlock Maily"):
        return

    from core.secret_file import SecretStoreError
    try:
        token = runtime.get_or_create_api_token()
    except SecretStoreError as e:
        # Unreadable secret store: stop without writing anything on it.
        fail_unreadable_secrets(e)
    months = settings.backfill_months
    # One sync at a time: the interface button and the automatic thread share
    # this lock.
    from core.auto_sync import AutoSync, serialized
    sync_fn = serialized(make_sync_fn(store, months))
    download_fn, inline_fn = make_attachment_fns(store, layout["attachments"])
    app = create_app(store, token, sync_fn=sync_fn,
                     send_fn=make_send_fn(store), act_fn=make_act_fn(store),
                     download_fn=download_fn, inline_fn=inline_fn,
                     labels_fn=make_labels_fn(store), frontend_dir=_frontend_dir(),
                     glass_fn=set_glass_alpha, glass_get_fn=get_glass_alpha,
                     add_google_fn=make_add_google_fn(store),
                     logout_fn=make_logout_fn(store),
                     eml_fn=make_eml_fn(store),
                     add_imap_fn=make_add_imap_fn(store))

    port = free_port()
    _start_server(app, port)
    base = f"http://127.0.0.1:{port}"
    if not wait_for_health(base):
        raise RuntimeError("The local server did not start in time.")
    runtime.write_runtime_file(layout["runtime_json"], "127.0.0.1", port, token=token)
    # Automatic sync of every mailbox while the window is open
    # (MAILY_POLL_INTERVAL_SECONDS, 180 by default).
    AutoSync(store, sync_fn, settings.poll_interval_seconds).start()

    win = webview.create_window("Maily", base, **window_kwargs(sys.platform))
    if sys.platform == "darwin":
        # Applies the transparency fix once the native webview is ready (the
        # `loaded` event guarantees that it exists).
        win.events.loaded += lambda: _apply_macos_transparency(win)
    # Persistent storage (no private mode). Preferences do not rely on it (see
    # core/prefs.py), but cookies and caches are kept between launches.
    storage = str(paths.runtime_dir() / "webview")
    webview.start(private_mode=False, storage_path=storage)


def parse_args(argv=None):
    """Command-line options of the launcher (all optional)."""
    import argparse
    ap = argparse.ArgumentParser(prog="maily", description="Maily, a local multi-account email client.")
    ap.add_argument("--data-dir", metavar="FOLDER",
                    help="folder of the local data (database, encrypted secrets). "
                         "Same as the MAILY_DATA_DIR variable.")
    return ap.parse_args(argv)


def main(argv=None):
    import os
    from core import paths
    args = parse_args(argv)
    if args.data_dir:
        os.environ[paths.DATA_DIR_ENV] = args.data_dir
    run()


if __name__ == "__main__":
    main()
