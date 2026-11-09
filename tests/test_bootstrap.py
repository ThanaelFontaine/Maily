import contextlib
from app import bootstrap


def test_free_port_returns_valid_port():
    p = bootstrap.free_port()
    assert isinstance(p, int) and 1024 < p < 65536


def test_wait_for_health_true():
    class FakeResp:
        status = 200

    @contextlib.contextmanager
    def opener(url, timeout=2):
        yield FakeResp()

    assert bootstrap.wait_for_health("http://x", _opener=opener, _sleep=lambda s: None) is True


def test_wait_for_health_false_on_error():
    def opener(url, timeout=2):
        raise OSError("refused")

    assert bootstrap.wait_for_health(
        "http://x", timeout=0.3, interval=0.1, _opener=opener, _sleep=lambda s: None
    ) is False


def test_make_sync_fn(monkeypatch):
    class FakeStore:
        def get_account(self, aid):
            return {"email": "me@example.com"} if aid == 1 else None

        def get_sync_state(self, aid, key):
            return "1"  # backfill deja fait -> chemin incremental

    import core.accounts_service as svc
    monkeypatch.setattr(svc, "sync_account", lambda store, email, aid, **kw: 42)

    fn = bootstrap.make_sync_fn(FakeStore())
    assert fn(1) == 42


def test_unreadable_secrets_are_shown_on_screen(monkeypatch, capsys):
    import pytest
    shown = []
    monkeypatch.setattr(bootstrap, "_show_fatal", lambda msg: shown.append(msg))
    with pytest.raises(SystemExit) as exc:
        bootstrap.fail_unreadable_secrets(RuntimeError("different key"))
    assert exc.value.code == 2
    assert shown == ["different key"]
    assert "different key" in capsys.readouterr().err


def test_fatal_page_escapes_message():
    page = bootstrap.fatal_page("<script>x</script> secrets.enc")
    assert "<script>x" not in page and "&lt;script&gt;" in page and "secrets.enc" in page


def _fake_launch(monkeypatch):
    """Runs bootstrap.run() with a fake window and no server; returns what it saw."""
    import sys
    import types
    from core import auto_sync

    class Event:
        def __iadd__(self, fn):
            return self

    seen = {}
    fake = types.SimpleNamespace(
        create_window=lambda title, url, **kw: seen.update(url=url) or types.SimpleNamespace(
            events=types.SimpleNamespace(loaded=Event())),
        start=lambda **kw: None)
    monkeypatch.setitem(sys.modules, "webview", fake)
    monkeypatch.setattr(bootstrap, "_start_server", lambda app, port: None)
    monkeypatch.setattr(bootstrap, "wait_for_health", lambda base, **kw: True)
    monkeypatch.setattr(bootstrap, "_apply_macos_transparency", lambda win: None)
    monkeypatch.setattr(auto_sync.AutoSync, "start", lambda self: None)
    import api.app
    monkeypatch.setattr(api.app, "create_app", lambda store, token, **kw: seen.update(token=token))
    bootstrap.run()
    return seen


def test_each_launch_has_its_own_token_in_runtime_json_and_the_window_address(monkeypatch):
    from core import paths, runtime, secret_file
    layout = paths.ensure_runtime_dirs(paths.runtime_dir())
    tokens = []
    for _ in range(2):
        seen = _fake_launch(monkeypatch)
        saved = runtime.read_runtime_file(layout["runtime_json"])
        assert saved["token"] == seen["token"]
        assert seen["url"].endswith("/#k=" + seen["token"])
        tokens.append(seen["token"])
    assert tokens[0] != tokens[1]
    assert secret_file.get("api_token") is None


def test_run_does_not_use_the_stored_token(monkeypatch):
    import inspect
    assert "get_or_create_api_token" not in inspect.getsource(bootstrap.run)


def test_claude_client_reads_the_token_from_runtime_json(monkeypatch):
    import importlib.util
    import pathlib
    from core import paths, runtime
    layout = paths.ensure_runtime_dirs(paths.runtime_dir())
    runtime.write_runtime_file(layout["runtime_json"], "127.0.0.1", 5000, token="tok-from-runtime")
    root = pathlib.Path(__file__).resolve().parent.parent
    spec = importlib.util.spec_from_file_location("claude_client", root / "scripts" / "claude_client.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod._base_and_token() == ("http://127.0.0.1:5000", "tok-from-runtime")


def test_the_keyring_migration_does_not_ask_for_the_api_token(monkeypatch):
    from core import secret_file
    asked = []
    monkeypatch.setattr(secret_file, "migrate_from_keyring", lambda names: asked.extend(names))

    class _Store:
        def list_accounts(self):
            return [{"email": "a@example.com"}]

    bootstrap._migrate_secrets(_Store())
    assert "api_token" not in asked
    assert "oauth_client" in asked and "account:a@example.com" in asked


def _render_inline(database, monkeypatch, tmp_path, mime, data=b"PNGDATA"):
    """GET /messages/{id}/html for a message whose cid: image has the given stored MIME type."""
    from fastapi.testclient import TestClient
    from api.app import create_app
    from core import accounts_service as svc
    from core.store import Store

    store = Store(database)
    a = store.upsert_account("me@example.com")
    mid = store.upsert_message(a, "g1", body_html='<img src="cid:logo1"><p>hi</p>')
    store.replace_attachments(mid, [{"filename": "logo", "mime_type": mime, "size": len(data),
                                     "gmail_attachment_id": "att1", "content_id": "logo1"}])
    monkeypatch.setattr(svc, "fetch_attachment", lambda *a, **k: (data, mime, "logo"))
    _download, inline_fn = bootstrap.make_attachment_fns(store, str(tmp_path))
    c = TestClient(create_app(store, "tok", inline_fn=inline_fn))
    return c.get(f"/messages/{mid}/html", headers={"Authorization": "Bearer tok"})


def test_inline_hostile_mime_leaves_cid_and_adds_no_remote_tag(database, monkeypatch, tmp_path):
    r = _render_inline(database, monkeypatch, tmp_path, 'image/x"><img src=https://evil.example>')
    assert "evil.example" not in r.text and "data:" not in r.text
    assert "cid:logo1" in r.text
    assert r.headers["X-Maily-Blocked-Remote"] == "0"


def test_inline_mime_is_normalised(database, monkeypatch, tmp_path):
    r = _render_inline(database, monkeypatch, tmp_path, "image/JPG; name=a.jpg")
    assert "data:image/jpeg;base64,UE5HREFUQQ==" in r.text and "cid:logo1" not in r.text
    assert r.headers["X-Maily-Blocked-Remote"] == "0"


def test_inline_svg_and_non_images_are_refused(database, monkeypatch, tmp_path):
    for mime in ("image/svg+xml", "text/html", "", None, "image/png\r\nX: y"):
        r = _render_inline(database, monkeypatch, tmp_path, mime)
        assert "data:" not in r.text and "cid:logo1" in r.text, mime


def test_inline_image_mime_allow_list():
    f = bootstrap.inline_image_mime
    assert f("image/png") == "image/png" and f(" IMAGE/PJPEG ; q=1") == "image/jpeg"
    assert f("image/x-png") == "image/png" and f("image/webp") == "image/webp"
    assert f("image/svg+xml") is None and f("image/png/x") is None and f(None) is None


def test_message_html_rejects_malformed_inline_uri(database):
    from fastapi.testclient import TestClient
    from api.app import create_app
    from core.store import Store

    store = Store(database)
    a = store.upsert_account("me@example.com")
    mid = store.upsert_message(a, "g1", body_html='<img src="cid:logo1">')
    store.replace_attachments(mid, [{"filename": "l", "mime_type": "image/png", "size": 1,
                                     "gmail_attachment_id": "a", "content_id": "logo1"}])
    bad = 'data:image/png;base64,AA"><img src=https://evil.example>'
    c = TestClient(create_app(store, "tok", inline_fn=lambda m, aid: bad))
    r = c.get(f"/messages/{mid}/html", headers={"Authorization": "Bearer tok"})
    assert "evil.example" not in r.text and "cid:logo1" in r.text
