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
