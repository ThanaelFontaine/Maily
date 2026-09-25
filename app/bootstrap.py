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


def _migrate_secrets(store) -> None:
    """Rapatrie les secrets du Trousseau vers le fichier chiffre (une seule fois)."""
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
    # En binaire figé (PyInstaller), le frontend est embarque a la racine.
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


# NSVisualEffectView (vibrancy) : material moderne translucide. Le material 0
# (AppearanceBased) est DEPRECIE (10.14) et rend opaque sur macOS 26. 21 =
# UnderWindowBackground, concu pour laisser voir le bureau depoli sous une fenetre.
_GLASS_MATERIAL = 21       # NSVisualEffectMaterialUnderWindowBackground
_GLASS_STATE_ACTIVE = 1    # NSVisualEffectStateActive
_GLASS_BLEND_BEHIND = 0    # NSVisualEffectBlendingModeBehindWindow
_GLASS_AUTORESIZE = 18     # NSViewWidthSizable(2) | NSViewHeightSizable(16)

# uids deja traites (le re-parentage ne doit se faire qu'une fois par fenetre).
_GLASS_DONE = set()
# Reference de la couche vibrancy par fenetre, pour regler sa densite (alphaValue)
# via le slider du frontend. alpha 1 = depoli plein ; 0 = bureau net.
_GLASS_VEV = {}
_GLASS_ALPHA_DEFAULT = 0.6


def _glass_alpha_path():
    from core import paths
    return paths.runtime_dir() / "glass_alpha"


def get_glass_alpha():
    """Densite du depoli persistee (0..1), defaut 0.6 - lue au demarrage."""
    try:
        return max(0.0, min(1.0, float(_glass_alpha_path().read_text().strip())))
    except Exception:
        return _GLASS_ALPHA_DEFAULT


def set_glass_alpha(alpha):
    """Regle la densite du depoli (vibrancy) + persiste - appele par l'API."""
    try:
        a = max(0.0, min(1.0, float(alpha)))
    except Exception:
        return
    try:  # persistance robuste (independante du localStorage / mode prive)
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
    # Revele le VRAI bureau DEPOLI (flou) derriere le chrome translucide (Verre).
    #
    # Sur macOS 26, deux choses masquaient le bureau :
    #   1. La WKWebView peignait une underPageBackgroundColor opaque (forcee clair)
    #      et la cle KVC `drawsTransparentBackground` de pywebview est deprecie/
    #      no-op (on utilise `drawsBackground`).
    #   2. pywebview ajoute la NSVisualEffectView EN SOUS-VUE de la WKWebView (qui
    #      EST la contentView). Imbriquee ainsi, la vibrancy "behind window" ne
    #      compose pas le bureau (aplat opaque) ; en plus son material par defaut
    #      (0) est deprecie.
    # Correctif : re-parenter -> contentView = conteneur portant [vibrancy au fond
    # (material 21), WKWebView transparente devant]. La vibrancy floute alors le
    # bureau et le contenu web transparent se pose dessus. Thread principal, 1x.
    #
    # Prerequis systeme : Reglages > Accessibilite > Ecran > Reduire la
    # transparence = OFF (sinon macOS force un fond opaque).
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
            webview = bv.webview  # WKWebView (WebKitHost), la contentView

            # 1) WKWebView reellement transparente (voie moderne).
            for setter in (
                lambda: webview.setValue_forKey_(False, "drawsBackground"),
                lambda: webview.setUnderPageBackgroundColor_(clear),
            ):
                try:
                    setter()
                except Exception:
                    pass

            # 2) Recupere/cree la vibrancy et lui donne un material translucide.
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

            # 3) Nouveau contentView = conteneur ; [vibrancy au fond, web devant].
            container = AppKit.NSView.alloc().initWithFrame_(webview.frame())
            container.setAutoresizesSubviews_(True)
            window.setContentView_(container)
            vev.setFrame_(container.bounds())
            vev.setAutoresizingMask_(_GLASS_AUTORESIZE)
            container.addSubview_(vev)
            webview.setFrame_(container.bounds())
            webview.setAutoresizingMask_(_GLASS_AUTORESIZE)
            container.addSubview_positioned_relativeTo_(webview, AppKit.NSWindowAbove, vev)

            # Densite reglable du depoli, restauree depuis la valeur persistee.
            _GLASS_VEV[win.uid] = vev
            vev.setAlphaValue_(get_glass_alpha())

            # 4) Fenetre transparente + active (recompositing live du bureau).
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

    # Secrets : migration unique Trousseau -> fichier chiffre local (supprime
    # l'invite de mot de passe du Trousseau dans l'app empaquetee), puis porte
    # Touch ID au lancement.
    _migrate_secrets(store)
    from core import biometric
    if not biometric.require_unlock("Deverrouiller Maily"):
        return

    token = runtime.get_or_create_api_token()
    from core.config import load_settings
    settings = load_settings()
    months = settings.backfill_months
    # Une seule synchro a la fois : le bouton de l'interface et le fil
    # automatique partagent ce verrou.
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
        raise RuntimeError("Le serveur local n'a pas demarre a temps.")
    runtime.write_runtime_file(layout["runtime_json"], "127.0.0.1", port)
    # Synchro automatique de toutes les boites tant que la fenetre est ouverte
    # (MAILY_POLL_INTERVAL_SECONDS, 180 par defaut).
    AutoSync(store, sync_fn, settings.poll_interval_seconds).start()

    win = webview.create_window("Maily", base, **window_kwargs(sys.platform))
    if sys.platform == "darwin":
        # Applique la correction de transparence une fois la webview native prete
        # (l'evenement `loaded` garantit son existence).
        win.events.loaded += lambda: _apply_macos_transparency(win)
    # Stockage persistant (pas de mode prive) : localStorage conserve entre deux
    # lancements -> theme, opacite du verre, largeur de la liste memorises.
    storage = str(paths.runtime_dir() / "webview")
    webview.start(private_mode=False, storage_path=storage)


if __name__ == "__main__":
    run()
