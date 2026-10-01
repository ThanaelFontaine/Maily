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
        bootstrap.fail_unreadable_secrets(RuntimeError("cle differente"))
    assert exc.value.code == 2
    assert shown == ["cle differente"]
    assert "cle differente" in capsys.readouterr().err


def test_fatal_page_escapes_message():
    page = bootstrap.fatal_page("<script>x</script> secrets.enc")
    assert "<script>x" not in page and "&lt;script&gt;" in page and "secrets.enc" in page
