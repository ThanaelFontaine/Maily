from __future__ import annotations
import json
import re
import pathlib
import urllib.parse
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from core.sanitize import sanitize_html_report

# Hotes acceptes dans l'en-tete Host (protection contre le DNS rebinding).
# Les tests ajoutent "testserver" (hote par defaut de TestClient) via
# tests/conftest.py ; il n'est jamais accepte en production.
_LOCAL_HOSTS = {"127.0.0.1", "localhost", "[::1]"}
_CATEGORY_LABELS = {
    "promotions": "CATEGORY_PROMOTIONS",
    "social": "CATEGORY_SOCIAL",
    "updates": "CATEGORY_UPDATES",
    "forums": "CATEGORY_FORUMS",
}


class SendPayload(BaseModel):
    account_id: int
    to: str
    subject: str = ""
    body_text: str = ""
    body_html: str | None = None
    cc: str | None = None
    in_reply_to: str | None = None
    thread_id: str | None = None
    attachments: list[dict] = []
    idempotency_key: str | None = None


class ModifyPayload(BaseModel):
    add_labels: list[str] = []
    remove_labels: list[str] = []


class ImapConnectPayload(BaseModel):
    email: str
    password: str
    host: str = "imap.orange.fr"
    port: int = 993


def create_app(store, token, sync_fn=None, send_fn=None, act_fn=None,
               download_fn=None, inline_fn=None, labels_fn=None, frontend_dir=None,
               glass_fn=None, glass_get_fn=None, add_google_fn=None,
               logout_fn=None, eml_fn=None, add_imap_fn=None) -> FastAPI:
    app = FastAPI(title="Maily API")

    def _host_ok(request: Request) -> bool:
        host = (request.headers.get("host") or "").split(":")[0]
        return host in _LOCAL_HOSTS

    async def guard(request: Request):
        if not _host_ok(request):
            raise HTTPException(status_code=403, detail="host not allowed")
        auth = request.headers.get("authorization", "")
        if auth != f"Bearer {token}":
            raise HTTPException(status_code=401, detail="unauthorized")

    def rows(rs):
        return [dict(r) for r in rs]

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/about", dependencies=[Depends(guard)])
    def about():
        import core
        from core import paths
        return {"version": core.__version__, "data_dir": str(paths.runtime_dir())}

    def _prefs_payload():
        from core import prefs
        return {"prefs": prefs.load(), "stored": sorted(prefs.stored_keys())}

    @app.get("/prefs", dependencies=[Depends(guard)])
    def prefs_get():
        # Preferences de l'interface (theme, mode Classic, images distantes,
        # largeur de liste), rangees dans prefs.json : le localStorage de la
        # webview ne survit pas au changement de port d'un lancement a l'autre.
        return _prefs_payload()

    @app.post("/prefs", dependencies=[Depends(guard)])
    async def prefs_post(request: Request):
        from core import prefs
        try:
            body = await request.json()
        except ValueError:
            raise HTTPException(status_code=400, detail="JSON invalide")
        try:
            prefs.update(body)
        except prefs.InvalidPref as e:
            raise HTTPException(status_code=400, detail=str(e))
        return _prefs_payload()

    @app.get("/glass", dependencies=[Depends(guard)])
    def glass_get():
        a = glass_get_fn() if glass_get_fn else 0.6
        return {"alpha": max(0.0, min(1.0, float(a)))}

    @app.post("/glass", dependencies=[Depends(guard)])
    async def glass(request: Request):
        # Regle la densite du depoli (vibrancy) du theme Verre, en direct.
        try:
            body = await request.json()
            a = float(body.get("alpha"))
        except (TypeError, ValueError, AttributeError):
            raise HTTPException(status_code=400, detail="alpha invalide")
        a = max(0.0, min(1.0, a))
        if glass_fn:
            glass_fn(a)
        return {"alpha": a}

    @app.get("/accounts", dependencies=[Depends(guard)])
    def accounts():
        return rows(store.list_accounts())

    @app.post("/accounts/google", dependencies=[Depends(guard)])
    def add_google():
        if add_google_fn is None:
            raise HTTPException(status_code=501, detail="add account not wired")
        from core.auth import ReauthRequired, AuthTimeout
        from core.accounts_service import AddAccountInProgress
        try:
            return add_google_fn()
        except ReauthRequired as e:
            raise HTTPException(status_code=400, detail=str(e))
        except AuthTimeout as e:
            raise HTTPException(status_code=408, detail=str(e))
        except AddAccountInProgress as e:
            raise HTTPException(status_code=409, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"ajout du compte echoue: {e}")

    @app.patch("/accounts/{account_id}", dependencies=[Depends(guard)])
    async def patch_account(account_id: int, request: Request):
        body = await request.json()
        dn = body.get("display_name")
        color = body.get("color")
        if dn is not None and not isinstance(dn, str):
            raise HTTPException(status_code=400, detail="display_name invalide")
        if color is not None and not re.fullmatch(r"#[0-9a-fA-F]{6}", color or ""):
            raise HTTPException(status_code=400, detail="color invalide")
        if store.get_account(account_id) is None:
            raise HTTPException(status_code=404, detail="compte introuvable")
        store.update_account(account_id, display_name=dn, color=color)
        return dict(store.get_account(account_id))

    @app.post("/accounts/imap", dependencies=[Depends(guard)])
    def add_imap(payload: ImapConnectPayload):
        if add_imap_fn is None:
            raise HTTPException(status_code=501, detail="add imap not wired")
        from core.imap_client import ImapError
        from core.accounts_service import AddAccountInProgress
        try:
            return add_imap_fn(payload.email, payload.password, payload.host, payload.port)
        except ImapError as e:
            raise HTTPException(status_code=400, detail=f"connexion Orange echouee: {e}")
        except AddAccountInProgress as e:
            raise HTTPException(status_code=409, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"ajout du compte echoue: {e}")

    @app.delete("/accounts/{account_id}", dependencies=[Depends(guard)])
    def delete_account(account_id: int):
        if logout_fn is None:
            raise HTTPException(status_code=501, detail="logout not wired")
        if store.get_account(account_id) is None:
            raise HTTPException(status_code=404, detail="compte introuvable")
        try:
            logout_fn(account_id)
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"deconnexion echouee: {e}")
        return {"ok": True}

    @app.get("/accounts/{account_id}/labels", dependencies=[Depends(guard)])
    def labels(account_id: int):
        labs = store.list_labels(account_id)
        if not labs and labels_fn:
            try:
                labels_fn(account_id)
            except Exception:
                pass
            labs = store.list_labels(account_id)
        return rows(labs)

    @app.get("/messages", dependencies=[Depends(guard)])
    def messages(account_id: int | None = None, category: str | None = None,
                 label: str | None = None, archived: bool = False, trashed: bool = False,
                 limit: int = 100, offset: int = 0):
        require, exclude = [], []
        if trashed:
            pass
        elif label:
            require.append(label)
        elif archived:
            exclude.append("INBOX")
        elif category:
            require.append("INBOX")
            if category == "primary":
                exclude += list(_CATEGORY_LABELS.values())
            elif category in _CATEGORY_LABELS:
                require.append(_CATEGORY_LABELS[category])
        else:
            require.append("INBOX")
        return rows(store.list_messages(account_id, require_labels=require, exclude_labels=exclude,
                                        trashed=trashed, limit=limit, offset=offset))

    @app.get("/threads", dependencies=[Depends(guard)])
    def threads(account_id: int | None = None, limit: int = 50, offset: int = 0):
        return rows(store.list_threads(account_id, limit, offset))

    @app.get("/threads/{thread_id}", dependencies=[Depends(guard)])
    def thread(thread_id: str, account_id: int | None = None):
        return rows(store.get_thread_messages(thread_id, account_id))

    @app.get("/messages/{message_id}", dependencies=[Depends(guard)])
    def message(message_id: int):
        m = store.get_message(message_id)
        if not m:
            raise HTTPException(status_code=404, detail="not found")
        return dict(m)

    @app.get("/messages/{message_id}/html", dependencies=[Depends(guard)])
    def message_html(message_id: int, allow_remote: bool = False):
        m = store.get_message(message_id)
        if not m:
            raise HTTPException(status_code=404, detail="not found")
        html, blocked = sanitize_html_report(m["body_html"] or "", allow_remote=allow_remote)
        if inline_fn:
            for att in store.list_attachments(message_id):
                cid = att["content_id"]
                if not cid:
                    continue
                pattern = re.compile("cid:" + re.escape(cid) + r"(?=[\"'\s>)]|$)")
                if pattern.search(html):
                    try:
                        uri = inline_fn(message_id, att["id"])
                    except Exception:
                        uri = None
                    if uri:
                        html = pattern.sub(lambda m: uri, html)
        # Nombre de ressources distantes retirees (pixels espions, images web) :
        # l'interface s'en sert pour proposer « Afficher les images ».
        return HTMLResponse(html, headers={"X-Maily-Blocked-Remote": str(blocked)})

    @app.get("/messages/{message_id}/eml", dependencies=[Depends(guard)])
    def message_eml(message_id: int):
        if eml_fn is None:
            raise HTTPException(status_code=501, detail="eml export not wired")
        if store.get_message(message_id) is None:
            raise HTTPException(status_code=404, detail="not found")
        try:
            data, filename = eml_fn(message_id)
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"export .eml echoue: {e}")
        fname = filename or f"message-{message_id}.eml"
        ascii_fallback = re.sub(r'[\r\n"]', "", fname.encode("ascii", "ignore").decode("ascii")) or "message.eml"
        utf8_star = urllib.parse.quote(fname, safe="")
        cd = f"attachment; filename=\"{ascii_fallback}\"; filename*=UTF-8''{utf8_star}"
        return Response(content=data, media_type="message/rfc822",
                        headers={"Content-Disposition": cd})

    @app.get("/messages/{message_id}/attachments", dependencies=[Depends(guard)])
    def attachments(message_id: int):
        return rows(store.list_attachments(message_id))

    @app.get("/messages/{message_id}/attachments/{att_id}/download", dependencies=[Depends(guard)])
    def download_att(message_id: int, att_id: int):
        if download_fn is None:
            raise HTTPException(status_code=501, detail="download not wired")
        try:
            data, mime, filename = download_fn(message_id, att_id)
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"telechargement echoue: {e}")
        fname = filename or "piece-jointe"
        ascii_fallback = re.sub(r'[\r\n"]', "", fname.encode("ascii", "ignore").decode("ascii")) or "piece-jointe"
        utf8_star = urllib.parse.quote(fname, safe="")
        cd = f"attachment; filename=\"{ascii_fallback}\"; filename*=UTF-8''{utf8_star}"
        return Response(content=data, media_type="application/octet-stream",
                        headers={"Content-Disposition": cd})

    @app.get("/search", dependencies=[Depends(guard)])
    def search(q: str, account_id: int | None = None, limit: int = 50):
        return rows(store.search_messages(q, account_id=account_id, limit=limit))

    @app.post("/accounts/{account_id}/sync", dependencies=[Depends(guard)])
    def sync(account_id: int):
        if sync_fn is None:
            raise HTTPException(status_code=501, detail="sync not wired")
        return {"changed": sync_fn(account_id)}

    @app.post("/send", dependencies=[Depends(guard)])
    def send_endpoint(payload: SendPayload):
        if send_fn is None:
            raise HTTPException(status_code=501, detail="send not wired")
        try:
            return send_fn(payload.model_dump())
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"envoi echoue: {e}")

    def _act(message_id, action, add=None, remove=None):
        if act_fn is None:
            raise HTTPException(status_code=501, detail="actions not wired")
        try:
            return act_fn(message_id, action, add, remove)
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"action echouee: {e}")

    @app.post("/messages/{message_id}/modify", dependencies=[Depends(guard)])
    def modify_msg(message_id: int, payload: ModifyPayload):
        return _act(message_id, "modify", payload.add_labels, payload.remove_labels)

    @app.post("/messages/{message_id}/trash", dependencies=[Depends(guard)])
    def trash_msg(message_id: int):
        return _act(message_id, "trash")

    @app.post("/messages/{message_id}/untrash", dependencies=[Depends(guard)])
    def untrash_msg(message_id: int):
        return _act(message_id, "untrash")

    if frontend_dir:
        fd = pathlib.Path(frontend_dir)
        app.mount("/static", StaticFiles(directory=str(fd)), name="static")

        @app.get("/", response_class=HTMLResponse)
        def index(request: Request):
            if not _host_ok(request):
                raise HTTPException(status_code=403, detail="host not allowed")
            html = (fd / "index.html").read_text(encoding="utf-8")
            inject = f"<script>window.MAILY_TOKEN={json.dumps(token)};</script>"
            return HTMLResponse(html.replace("</head>", inject + "</head>"))

    return app
