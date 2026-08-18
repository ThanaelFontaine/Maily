from __future__ import annotations
import json
import pathlib
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from core.sanitize import sanitize_html

_LOCAL_HOSTS = {"127.0.0.1", "localhost", "[::1]", "testserver"}


def create_app(store, token, sync_fn=None, frontend_dir=None) -> FastAPI:
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
        return HTMLResponse(sanitize_html(m["body_html"] or "", allow_remote=allow_remote))

    @app.get("/search", dependencies=[Depends(guard)])
    def search(q: str, account_id: int | None = None, limit: int = 50):
        return rows(store.search_messages(q, account_id=account_id, limit=limit))

    @app.post("/accounts/{account_id}/sync", dependencies=[Depends(guard)])
    def sync(account_id: int):
        if sync_fn is None:
            raise HTTPException(status_code=501, detail="sync not wired")
        return {"changed": sync_fn(account_id)}

    if frontend_dir:
        fd = pathlib.Path(frontend_dir)
        app.mount("/static", StaticFiles(directory=str(fd)), name="static")

        @app.get("/", response_class=HTMLResponse)
        def index():
            html = (fd / "index.html").read_text(encoding="utf-8")
            inject = f"<script>window.MAILY_TOKEN={json.dumps(token)};</script>"
            return HTMLResponse(html.replace("</head>", inject + "</head>"))

    return app
