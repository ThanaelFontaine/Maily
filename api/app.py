from __future__ import annotations
import json
import pathlib
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from core.sanitize import sanitize_html

_LOCAL_HOSTS = {"127.0.0.1", "localhost", "[::1]", "testserver"}


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


class ModifyPayload(BaseModel):
    add_labels: list[str] = []
    remove_labels: list[str] = []


def create_app(store, token, sync_fn=None, send_fn=None, act_fn=None,
               download_fn=None, inline_fn=None, frontend_dir=None) -> FastAPI:
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

    @app.get("/accounts", dependencies=[Depends(guard)])
    def accounts():
        return rows(store.list_accounts())

    @app.get("/messages", dependencies=[Depends(guard)])
    def messages(account_id: int | None = None, label: str | None = None,
                 limit: int = 50, offset: int = 0):
        return rows(store.list_messages(account_id, label, limit, offset))

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
        html = sanitize_html(m["body_html"] or "", allow_remote=allow_remote)
        if inline_fn:
            for att in store.list_attachments(message_id):
                cid = att["content_id"]
                if cid and f"cid:{cid}" in html:
                    try:
                        uri = inline_fn(message_id, att["id"])
                    except Exception:
                        uri = None
                    if uri:
                        html = html.replace(f"cid:{cid}", uri)
        return HTMLResponse(html)

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
        safe = (filename or "piece-jointe").replace('"', "").replace("\n", " ")
        return Response(content=data, media_type="application/octet-stream",
                        headers={"Content-Disposition": f'attachment; filename="{safe}"'})

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
        def index():
            html = (fd / "index.html").read_text(encoding="utf-8")
            inject = f"<script>window.MAILY_TOKEN={json.dumps(token)};</script>"
            return HTMLResponse(html.replace("</head>", inject + "</head>"))

    return app
