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
            raise ValueError(f"compte {account_id} introuvable")
        # Premiere synchro : backfill borne (fenetre en mois) ; ensuite incremental.
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
            raise ValueError(f"compte {payload['account_id']} introuvable")
        return send_from_account(store, acc["email"], payload["account_id"], payload)

    return _send


def make_labels_fn(store):
    from core import accounts_service as svc

    def _labels(account_id):
        acc = store.get_account(account_id)
        if not acc:
            raise ValueError(f"compte {account_id} introuvable")
        return svc.refresh_labels(store, acc["email"], account_id)

    return _labels


def make_act_fn(store):
    from core import accounts_service as svc

    def _act(message_id, action, add=None, remove=None):
        m = store.get_message(message_id)
        if not m:
            raise ValueError("message introuvable")
        acc = store.get_account(m["account_id"])
        email = acc["email"]
        if action == "modify":
            return svc.modify_message(store, email, message_id, add=add, remove=remove)
        if action == "trash":
            return svc.trash_message(store, email, message_id)
        if action == "untrash":
            return svc.untrash_message(store, email, message_id)
        raise ValueError(f"action inconnue: {action}")

    return _act


def _frontend_dir() -> pathlib.Path:
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


# NSVisualEffectView : material moderne translucide. Le material 0
# (AppearanceBased) est DEPRECIE depuis 10.14 et, sur macOS 26, se replie sur un
# remplissage OPAQUE. 21 = UnderWindowBackground, concu pour laisser voir le
# bureau depoli sous le fond d'une fenetre.
_GLASS_MATERIAL = 21       # NSVisualEffectMaterialUnderWindowBackground
_GLASS_STATE_ACTIVE = 1    # NSVisualEffectStateActive
_GLASS_BLEND_BEHIND = 0    # NSVisualEffectBlendingModeBehindWindow
_GLASS_AUTORESIZE = 18     # NSViewWidthSizable(2) | NSViewHeightSizable(16)

# uids deja traites (le re-parentage ne doit se faire qu'une fois par fenetre).
_GLASS_DONE = set()


def _apply_macos_transparency(win):
    # Revele le VRAI bureau depoli derriere le chrome translucide (theme Verre).
    #
    # Deux causes empechaient de voir le bureau sur macOS 26 :
    #   1. La WKWebView peignait une underPageBackgroundColor opaque (corrige en
    #      la forcant a clair) ; la cle KVC `drawsTransparentBackground` posee par
    #      pywebview est deprecie/no-op sur 26 (on utilise `drawsBackground`).
    #   2. pywebview place sa NSVisualEffectView (vibrancy) EN SOUS-VUE de la
    #      WKWebView, qui EST la contentView. Imbriquee ainsi, la vibrancy
    #      "behind window" ne compose pas le bureau : elle rend un aplat opaque.
    # Correctif : re-parenter la hierarchie -> contentView = conteneur portant
    # [NSVisualEffectView au fond (material 21), WKWebView transparente devant].
    # Ainsi la vibrancy floute reellement le bureau et le contenu web transparent
    # se pose par-dessus. Tout se fait sur le thread principal, une seule fois.
    #
    # Prerequis systeme (sinon aucun material ne laisse voir le bureau) :
    # Reglages > Accessibilite > Ecran > Reduire la transparence = OFF.
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
            webview = bv.webview  # WKWebView (WebKitHost), actuelle contentView

            # WKWebView transparente (voie moderne).
            for setter in (
                lambda: webview.setValue_forKey_(False, "drawsBackground"),
                lambda: webview.setUnderPageBackgroundColor_(clear),
            ):
                try:
                    setter()
                except Exception:
                    pass

            # Recupere la NSVisualEffectView posee par pywebview (ou en cree une).
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

            # Nouveau contentView = conteneur ; empile [vibrancy au fond, web devant].
            container = AppKit.NSView.alloc().initWithFrame_(webview.frame())
            container.setAutoresizesSubviews_(True)
            window.setContentView_(container)   # detache la webview de la contentView

            vev.setFrame_(container.bounds())
            vev.setAutoresizingMask_(_GLASS_AUTORESIZE)
            container.addSubview_(vev)

            webview.setFrame_(container.bounds())
            webview.setAutoresizingMask_(_GLASS_AUTORESIZE)
            container.addSubview_positioned_relativeTo_(webview, AppKit.NSWindowAbove, vev)

            window.makeFirstResponder_(webview)
            window.setOpaque_(False)
            window.setBackgroundColor_(clear)
        except Exception:
            pass

    AppHelper.callAfter(_set)


def window_kwargs(platform: str, width: int = 1240, height: int = 820) -> dict:
    # Transparence de la fenetre native selon la plateforme :
    # macOS -> vibrancy (flou depoli natif du bureau) ; Linux -> transparent
    # (le compositeur floute) ; ailleurs (Windows) -> opaque + fond de repli clair.
    kwargs = {"width": width, "height": height}
    if platform == "darwin":
        kwargs["transparent"] = True
        kwargs["vibrancy"] = True
    elif platform.startswith("linux"):
        kwargs["transparent"] = True
    else:
        kwargs["background_color"] = "#EDF0FB"
    return kwargs


def run():
    import webview
    from core import paths, runtime
    from core.db import Database
    from core.store import Store
    from api.app import create_app

    layout = paths.ensure_runtime_dirs(paths.runtime_dir())
    db = Database(layout["db"])
    store = Store(db)
    token = runtime.get_or_create_api_token()
    from core.config import load_settings
    months = load_settings().backfill_months
    download_fn, inline_fn = make_attachment_fns(store, layout["attachments"])
    app = create_app(store, token, sync_fn=make_sync_fn(store, months),
                     send_fn=make_send_fn(store), act_fn=make_act_fn(store),
                     download_fn=download_fn, inline_fn=inline_fn,
                     labels_fn=make_labels_fn(store), frontend_dir=_frontend_dir())

    port = free_port()
    _start_server(app, port)
    base = f"http://127.0.0.1:{port}"
    if not wait_for_health(base):
        raise RuntimeError("Le serveur local n'a pas demarre a temps.")
    runtime.write_runtime_file(layout["runtime_json"], "127.0.0.1", port)

    win = webview.create_window("Maily", base, **window_kwargs(sys.platform))
    if sys.platform == "darwin":
        # Applique la correction de transparence une fois la webview native prete
        # (l'evenement `loaded` garantit son existence).
        win.events.loaded += lambda: _apply_macos_transparency(win)
    webview.start()


if __name__ == "__main__":
    run()
