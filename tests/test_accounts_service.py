from core import accounts_service as svc


def test_build_gmail_client(monkeypatch):
    monkeypatch.setattr(svc, "load_credentials", lambda e: "CREDS")
    captured = {}

    def fake_build(*a, **k):
        captured["svc"] = (a, k)
        return "SERVICE"

    monkeypatch.setattr(svc, "build", fake_build)
    client = svc.build_gmail_client("me@example.org")
    assert client.service == "SERVICE"
    assert captured["svc"][0] == ("gmail", "v1")
    assert captured["svc"][1]["credentials"] == "CREDS"


def test_sync_account_calls_incremental(monkeypatch):
    calls = {}

    class FakeSyncer:
        def __init__(self, store, client, account_id):
            calls["init"] = (store, client, account_id)

        def incremental(self):
            calls["mode"] = "inc"
            return 3

        def backfill(self, query=None):
            calls["mode"] = "full"
            return 5

    monkeypatch.setattr(svc, "build_gmail_client", lambda e: "CLIENT")
    monkeypatch.setattr(svc, "Syncer", FakeSyncer)
    n = svc.sync_account("STORE", "me@example.org", 1)
    assert n == 3 and calls["mode"] == "inc"
    n2 = svc.sync_account("STORE", "me@example.org", 1, full=True)
    assert n2 == 5 and calls["mode"] == "full"
