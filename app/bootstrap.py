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
# remplissage OPAQUE sombre. 21 = UnderWindowBackground, le plus translucide,
# concu pour laisser voir le bureau depoli sous le fond de la fenetre.
_GLASS_MATERIAL = 21       # NSVisualEffectMaterialUnderWindowBackground
_GLASS_STATE_ACTIVE = 1    # NSVisualEffectStateActive
_GLASS_BLEND_BEHIND = 0    # NSVisualEffectBlendingModeBehindWindow


def _apply_macos_transparency(win):
    # Revele le VRAI bureau depoli derriere le chrome translucide (theme Verre).
    #
    # Cause racine du fond charcoal opaque : pywebview cree une NSVisualEffectView
    # (sous-vue de la WKWebView, qui EST la contentView) mais n'appelle jamais
    # setMaterial_. Elle reste donc sur material=0 (AppearanceBased, deprecie
    # 10.14), qui sur macOS 26 se replie sur un remplissage opaque sombre = le
    # charcoal observe. Correctif : forcer un material moderne translucide +
    # apparence claire, IN PLACE, sur le thread principal. On renforce aussi la
    # transparence de la WKWebView par la voie moderne (la cle KVC
    # `drawsTransparentBackground` posee par pywebview est deprecie/no-op sur 26).
    #
    # Prerequis systeme (sinon aucun material ne laisse voir le bureau) :
    # Reglages > Accessibilite > Ecran > Reduire la transparence = OFF.
    try:
        import webview.platforms.cocoa as cocoa
        import AppKit
        from PyObjCTools import AppHelper
    except Exception:
        return
    bv = cocoa.BrowserView.instances.get(win.uid)
    if bv is None:
        return

    def _set():
        clear = AppKit.NSColor.clearColor()
        window = bv.window
        webview = bv.webview  # WKWebView (WebKitHost) == window.contentView()

        # 1) Fenetre transparente (re-assure ; deja pose par pywebview).
        try:
            window.setOpaque_(False)
            window.setBackgroundColor_(clear)
        except Exception:
            pass

        # 2) WKWebView transparente (voie moderne).
        for setter in (
            lambda: webview.setUnderPageBackgroundColor_(clear),
            lambda: webview.setValue_forKey_(False, "drawsBackground"),
        ):
            try:
                setter()
            except Exception:
                pass

        # 3) Recupere la NSVisualEffectView existante (celle a material=0).
        vev = None
        try:
            for sub in webview.subviews():
                if sub.isKindOfClass_(AppKit.NSVisualEffectView):
                    vev = sub
                    break
        except Exception:
            pass
        if vev is None:
            return

        # 4) LE correctif : material moderne translucide -> bureau depoli visible.
        for setter in (
            lambda: vev.setMaterial_(_GLASS_MATERIAL),       # 0 (opaque) -> 21
            lambda: vev.setBlendingMode_(_GLASS_BLEND_BEHIND),
            lambda: vev.setState_(_GLASS_STATE_ACTIVE),
            lambda: vev.setEmphasized_(True),
        ):
            try:
                setter()
            except Exception:
                pass

        # 5) Depoli CLAIR meme en mode sombre : apparence claire sur la seule vibrancy.
        try:
            light = AppKit.NSAppearance.appearanceNamed_(AppKit.NSAppearanceNameVibrantLight)
            if light is not None:
                vev.setAppearance_(light)
        except Exception:
            pass

        # 6) Remplit / suit la fenetre et force un redraw.
        try:
            vev.setAutoresizingMask_(AppKit.NSViewWidthSizable | AppKit.NSViewHeightSizable)
            vev.setFrame_(webview.bounds())
            vev.setNeedsDisplay_(True)
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
