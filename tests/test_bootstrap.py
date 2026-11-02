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
