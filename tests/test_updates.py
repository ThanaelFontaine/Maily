"""Update check (core/updates.py and the /update routes): no real network, ever."""
import datetime
import json
import os
import stat
import pytest
from fastapi.testclient import TestClient
from api.app import create_app
from core import paths, prefs, updates
from core.store import Store
import core

TOKEN = "tok"


def _auth():
    return {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture
def fetch(monkeypatch):
    """Replaces the network call; `fetch.calls` counts it, `fetch.answer` drives it."""
    class Fake:
        calls = 0
        answer = ("v99.0.0", "https://github.com/ThanaelFontaine/Maily/releases/tag/v99.0.0")

        def __call__(self):
            Fake.calls += 1
            if isinstance(self.answer, Exception):
                raise self.answer
            return self.answer

    f = Fake()
    f.calls = 0
    monkeypatch.setattr(updates, "fetch_latest", f)
    return f


def _calls(f):
    return type(f).calls


def _write_cache(latest, age_hours):
    when = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=age_hours)
    p = paths.runtime_dir() / "update.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"checked_at": when.isoformat(), "latest": latest, "url": "u"}), encoding="utf-8")


def _bump(patch=1):
    major, minor, micro = updates.parse_version(core.__version__)
    return f"v{major}.{minor}.{micro + patch}"


@pytest.mark.parametrize("tag,expected", [
    ("v0.9.0", (0, 9, 0)), ("0.9.0", (0, 9, 0)), (" v1.10.2 ", (1, 10, 2)),
    ("v0.9.0-rc1", None), ("latest", None), ("", None), ("v", None), (None, None), (5, None),
    ("v1..2", None),
])
def test_parse_version(tag, expected):
    assert updates.parse_version(tag) == expected


def test_newer_release_is_available(fetch):
    fetch.answer = (_bump(), "https://example/r")
    out = updates.check()
    assert out["enabled"] and out["available"] is True and out["failed"] is False
    assert out["latest"] == _bump().removeprefix("v") and out["current"] == core.__version__
    assert out["kind"] == "source" and out["checked_at"]


def test_equal_release_is_not_an_update(fetch):
    fetch.answer = ("v" + core.__version__, "u")
    assert updates.check()["available"] is False


def test_older_release_is_not_an_update(fetch):
    fetch.answer = ("v0.0.1", "u")
    assert updates.check()["available"] is False


def test_ten_is_greater_than_nine(fetch, monkeypatch):
    monkeypatch.setattr(core, "__version__", "0.9.0")
    fetch.answer = ("v0.10.0", "u")
    assert updates.check()["available"] is True


@pytest.mark.parametrize("tag", ["nightly", "v1.x.0", "v1.0.0-rc1", ""])
def test_unparsable_tag_means_no_update(fetch, tag):
    fetch.answer = (tag, "u")
    out = updates.check()
    assert out["available"] is False and out["latest"] is None


def test_packaged_app_kind(fetch, monkeypatch):
    monkeypatch.setattr("sys.frozen", True, raising=False)
    assert updates.check()["kind"] == "app"


def test_cache_file_is_private_and_prevents_a_second_call(fetch):
    fetch.answer = (_bump(), "u")
    first = updates.check()
    second = updates.check()
    assert _calls(fetch) == 1 and second == first
    p = paths.runtime_dir() / "update.json"
    assert set(json.loads(p.read_text())) == {"checked_at", "latest", "url"}
    if os.name == "posix":
        assert stat.S_IMODE(p.stat().st_mode) == 0o600


def test_force_bypasses_the_cache(fetch):
    updates.check()
    updates.check(force=True)
    assert _calls(fetch) == 2


def test_cache_older_than_24h_is_refreshed(fetch):
    _write_cache("0.0.1", age_hours=25)
    out = updates.check()
    assert _calls(fetch) == 1 and out["latest"] == "99.0.0"


def test_cache_younger_than_24h_is_used(fetch):
    _write_cache(_bump().removeprefix("v"), age_hours=23)
    out = updates.check()
    assert _calls(fetch) == 0 and out["available"] is True


@pytest.mark.parametrize("error", [OSError("offline"), TimeoutError(), ValueError("bad json"), KeyError("tag_name")])
def test_network_error_keeps_the_last_value(fetch, error):
    _write_cache(_bump().removeprefix("v"), age_hours=30)
    fetch.answer = error
    out = updates.check()
    assert _calls(fetch) == 1
    assert out["available"] is True and out["failed"] is True
    # The remembered answer is untouched, so the next call tries again.
    assert json.loads((paths.runtime_dir() / "update.json").read_text())["latest"] == _bump().removeprefix("v")


def test_network_error_without_memory_means_no_update(fetch):
    fetch.answer = OSError("offline")
    out = updates.check()
    assert out["available"] is False and out["latest"] is None and out["failed"] is True
    assert not (paths.runtime_dir() / "update.json").exists()


def test_damaged_cache_is_ignored(fetch):
    p = paths.runtime_dir() / "update.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("{not json", encoding="utf-8")
    assert updates.check()["latest"] == "99.0.0" and _calls(fetch) == 1


def test_pref_off_means_no_network_call(fetch):
    prefs.update({"check_updates": False})
    out = updates.check(force=True)
    assert _calls(fetch) == 0
    assert out["enabled"] is False and out["available"] is False and out["latest"] is None
    assert not (paths.runtime_dir() / "update.json").exists()


def test_demo_mode_means_no_network_call(fetch):
    out = updates.check(force=True, offline=True)
    assert _calls(fetch) == 0 and out["enabled"] is False


def test_real_request_has_the_expected_headers(monkeypatch):
    seen = {}

    class Resp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b'{"tag_name": "v1.2.3", "html_url": "https://x/y"}'

    def fake_urlopen(req, timeout, context=None):
        seen.update(url=req.full_url, headers={k.lower(): v for k, v in req.header_items()}, timeout=timeout,
                    context=context)
        return Resp()

    monkeypatch.setattr(updates.urllib.request, "urlopen", fake_urlopen)
    assert updates.fetch_latest() == ("v1.2.3", "https://x/y")
    assert seen["url"] == "https://api.github.com/repos/ThanaelFontaine/Maily/releases/latest"
    assert seen["headers"]["accept"] == "application/vnd.github+json"
    assert seen["headers"]["user-agent"] == f"Maily/{core.__version__}"
    assert 0 < seen["timeout"] <= 10
    # certifi's CA bundle: the system paths may not exist inside the packaged app
    assert isinstance(seen["context"], updates.ssl.SSLContext)
    assert seen["context"].verify_mode == updates.ssl.CERT_REQUIRED


# --- preference ---

def test_check_updates_pref_defaults_to_true_and_is_boolean():
    assert prefs.load()["check_updates"] is True
    assert prefs.update({"check_updates": False})["check_updates"] is False
    with pytest.raises(prefs.InvalidPref):
        prefs.update({"check_updates": "no"})
    assert prefs.load()["check_updates"] is False


# --- API routes ---

@pytest.fixture
def client(database):
    return TestClient(create_app(Store(database), TOKEN))


def test_routes_require_the_token(client):
    assert client.get("/update").status_code == 401
    assert client.post("/update/check").status_code == 401
    assert client.post("/update/open").status_code == 401


def test_get_update_uses_the_cache_and_check_forces(client, fetch):
    fetch.answer = (_bump(), "u")
    r = client.get("/update", headers=_auth())
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"enabled", "current", "latest", "available", "kind", "checked_at", "failed"}
    assert body["available"] is True
    client.get("/update", headers=_auth())
    assert _calls(fetch) == 1
    assert client.post("/update/check", headers=_auth()).json()["available"] is True
    assert _calls(fetch) == 2


def test_routes_never_fail_when_offline(client, fetch):
    fetch.answer = OSError("offline")
    r = client.get("/update", headers=_auth())
    assert r.status_code == 200 and r.json()["failed"] is True and r.json()["available"] is False


def test_demo_app_never_calls_the_network(database, fetch):
    c = TestClient(create_app(Store(database), TOKEN, offline=True))
    assert c.get("/update", headers=_auth()).json()["enabled"] is False
    assert c.post("/update/check", headers=_auth()).json()["enabled"] is False
    assert _calls(fetch) == 0


def test_pref_is_served_and_saved_through_prefs_route(client):
    assert client.get("/prefs", headers=_auth()).json()["prefs"]["check_updates"] is True
    r = client.post("/prefs", headers=_auth(), json={"check_updates": False})
    assert r.json()["prefs"]["check_updates"] is False and r.json()["stored"] == ["check_updates"]
    assert client.post("/prefs", headers=_auth(), json={"check_updates": 1}).status_code == 400
    assert client.get("/update", headers=_auth()).json()["enabled"] is False


@pytest.fixture
def opened(monkeypatch):
    urls = []
    monkeypatch.setattr("webbrowser.open", lambda url, *a, **k: urls.append(url) or True)
    return urls


def test_open_source_goes_to_the_github_release_page(client, opened):
    assert client.post("/update/open", headers=_auth()).json() == {"ok": True}
    assert opened == ["https://github.com/ThanaelFontaine/Maily/releases/latest"]


@pytest.mark.parametrize("language,url", [
    ("fr", "https://maily.thanaelfontaine.eu/fr/telecharger/"),
    ("en", "https://maily.thanaelfontaine.eu/download/"),
    ("de", "https://maily.thanaelfontaine.eu/download/"),
    (None, "https://maily.thanaelfontaine.eu/download/"),
])
def test_open_packaged_app_goes_to_the_download_page(client, opened, monkeypatch, language, url):
    monkeypatch.setattr("sys.frozen", True, raising=False)
    prefs.update({"language": language})
    client.post("/update/open", headers=_auth())
    assert opened == [url]


def test_open_ignores_anything_the_request_sends(client, opened):
    client.post("/update/open", headers=_auth(), json={"url": "https://evil.example/"})
    client.post("/update/open?url=https://evil.example/", headers=_auth())
    assert opened == ["https://github.com/ThanaelFontaine/Maily/releases/latest"] * 2


def test_open_is_refused_in_demo_mode(database, opened):
    c = TestClient(create_app(Store(database), TOKEN, offline=True))
    assert c.post("/update/open", headers=_auth()).status_code == 403
    assert opened == []
