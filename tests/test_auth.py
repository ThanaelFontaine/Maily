import pytest
from google.auth.exceptions import RefreshError
from core import auth, secrets_store


@pytest.fixture(autouse=True)
def tmp_secret_store(monkeypatch, tmp_path):
    from core import secret_file
    monkeypatch.setattr(secret_file.paths, "runtime_dir", lambda override=None: tmp_path)
    return tmp_path


def test_scopes_are_minimal():
    assert "https://www.googleapis.com/auth/gmail.modify" in auth.SCOPES
    assert "https://www.googleapis.com/auth/gmail.send" in auth.SCOPES
    assert not any("mail.google.com" in s for s in auth.SCOPES)


def test_creds_dict_roundtrip():
    d = {
        "token": "ya29.x", "refresh_token": "1//r",
        "token_uri": "https://oauth2.googleapis.com/token",
        "client_id": "cid", "client_secret": "sec",
        "scopes": auth.SCOPES,
    }
    creds = auth.dict_to_creds(d)
    out = auth.creds_to_dict(creds)
    assert out["refresh_token"] == "1//r"
    assert out["client_id"] == "cid"
    assert out["scopes"] == auth.SCOPES


def test_load_credentials_refreshes_and_persists(monkeypatch):
    secrets_store.save_client_config("cid", "sec")
    secrets_store.save_account_token("me@example.com", {
        "token": "old", "refresh_token": "1//r",
        "token_uri": "https://oauth2.googleapis.com/token",
        "client_id": "cid", "client_secret": "sec", "scopes": auth.SCOPES,
    })

    def fake_refresh(self, request):
        self.token = "new-token"
    monkeypatch.setattr("google.oauth2.credentials.Credentials.refresh", fake_refresh)
    monkeypatch.setattr("google.oauth2.credentials.Credentials.expired", property(lambda self: True))

    creds = auth.load_credentials("me@example.com")
    assert creds.token == "new-token"
    assert secrets_store.load_account_token("me@example.com")["token"] == "new-token"


def test_load_credentials_reauth_on_refresh_error(monkeypatch):
    secrets_store.save_client_config("cid", "sec")
    secrets_store.save_account_token("me@example.com", {
        "token": "old", "refresh_token": "1//r",
        "token_uri": "https://oauth2.googleapis.com/token",
        "client_id": "cid", "client_secret": "sec", "scopes": auth.SCOPES,
    })

    def boom(self, request):
        raise RefreshError("invalid_grant")
    monkeypatch.setattr("google.oauth2.credentials.Credentials.refresh", boom)
    monkeypatch.setattr("google.oauth2.credentials.Credentials.expired", property(lambda self: True))

    with pytest.raises(auth.ReauthRequired):
        auth.load_credentials("me@example.com")


def test_load_credentials_reauth_when_no_token():
    with pytest.raises(auth.ReauthRequired):
        auth.load_credentials("absent@example.com")


def test_client_config_dict_reauth_when_absent():
    with pytest.raises(auth.ReauthRequired):
        auth.client_config_dict()


def test_run_local_auth_persists_token(monkeypatch):
    secrets_store.save_client_config("cid", "sec")

    class FakeCreds:
        token = "ya29.new"
        refresh_token = "1//r"
        token_uri = "https://oauth2.googleapis.com/token"
        client_id = "cid"
        client_secret = "sec"
        scopes = auth.SCOPES
        expiry = None

    class FakeFlow:
        @staticmethod
        def from_client_config(cfg, scopes):
            assert "installed" in cfg
            assert scopes == auth.SCOPES
            return FakeFlow()

        def run_local_server(self, **kw):
            assert kw.get("host") == "127.0.0.1"
            assert kw.get("port") == 0
            self.credentials = FakeCreds()
            return self.credentials

    monkeypatch.setattr(auth, "InstalledAppFlow", FakeFlow)
    monkeypatch.setattr(auth, "_fetch_email", lambda creds: "me@example.com")

    email = auth.run_local_auth(open_browser=False)
    assert email == "me@example.com"
    assert secrets_store.load_account_token("me@example.com")["refresh_token"] == "1//r"


def test_run_local_auth_forwards_timeout(monkeypatch):
    secrets_store.save_client_config("cid", "sec")
    captured = {}

    class FakeCreds:
        token = "t"; refresh_token = "1//r"; token_uri = "u"
        client_id = "cid"; client_secret = "sec"; scopes = auth.SCOPES; expiry = None

    class FakeFlow:
        @staticmethod
        def from_client_config(cfg, scopes):
            return FakeFlow()

        def run_local_server(self, **kw):
            captured.update(kw)
            return FakeCreds()

    monkeypatch.setattr(auth, "InstalledAppFlow", FakeFlow)
    monkeypatch.setattr(auth, "_fetch_email", lambda creds: "me@example.com")

    auth.run_local_auth(open_browser=False, timeout_seconds=90)
    assert captured.get("timeout_seconds") == 90


def test_run_local_auth_timeout_raises(monkeypatch):
    secrets_store.save_client_config("cid", "sec")

    class FakeFlow:
        @staticmethod
        def from_client_config(cfg, scopes):
            return FakeFlow()

        def run_local_server(self, **kw):
            return None  # aucun consentement recu dans le delai

    monkeypatch.setattr(auth, "InstalledAppFlow", FakeFlow)

    with pytest.raises(auth.AuthTimeout):
        auth.run_local_auth(open_browser=False, timeout_seconds=1)


def test_run_local_auth_maps_wsgi_timeout(monkeypatch):
    secrets_store.save_client_config("cid", "sec")

    class FakeFlow:
        @staticmethod
        def from_client_config(cfg, scopes):
            return FakeFlow()

        def run_local_server(self, **kw):
            raise auth.WSGITimeoutError("timed out")  # comportement reel de la lib

    monkeypatch.setattr(auth, "InstalledAppFlow", FakeFlow)

    with pytest.raises(auth.AuthTimeout):
        auth.run_local_auth(open_browser=False, timeout_seconds=1)
