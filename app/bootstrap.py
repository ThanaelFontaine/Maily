from __future__ import annotations
import socket
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
                     frontend_dir=_frontend_dir())

    port = free_port()
    _start_server(app, port)
    base = f"http://127.0.0.1:{port}"
    if not wait_for_health(base):
        raise RuntimeError("Le serveur local n'a pas demarre a temps.")
    runtime.write_runtime_file(layout["runtime_json"], "127.0.0.1", port)

    webview.create_window("Maily", base, width=1240, height=820)
    webview.start()


if __name__ == "__main__":
    run()
