import json
import os
import stat
import pytest
from fastapi.testclient import TestClient
from api.app import create_app
from core import paths, prefs
from core.store import Store

TOKEN = "tok"


def _auth():
    return {"Authorization": f"Bearer {TOKEN}"}


def test_defaults_without_file():
    assert prefs.load() == {"theme": "classic", "classic_mode": "auto", "remote_images": False,
                            "check_updates": True, "list_width": None, "language": None}
    assert prefs.stored_keys() == set()


def test_update_persists_in_data_dir_with_owner_only_perms():
    out = prefs.update({"theme": "zeroday", "remote_images": True})
    assert out["theme"] == "zeroday" and out["remote_images"] is True
    p = paths.runtime_dir() / "prefs.json"
    assert json.loads(p.read_text()) == {"remote_images": True, "theme": "zeroday"}
    if os.name == "posix":
        assert stat.S_IMODE(p.stat().st_mode) == 0o600
    # A "new launch" reads the file again: nothing depends on the port or the webview.
    assert prefs.load()["theme"] == "zeroday"
    assert prefs.stored_keys() == {"theme", "remote_images"}


@pytest.mark.parametrize("bad", [
    {"theme": "pink"}, {"classic_mode": "night"}, {"remote_images": "yes"}, {"check_updates": "yes"},
    {"list_width": "wide"}, {"unknown": 1}, ["theme"], {"language": "it"}, {"language": "EN"},
])
def test_invalid_updates_are_rejected_without_writing(bad):
    prefs.update({"theme": "aero"})
    with pytest.raises(prefs.InvalidPref):
        prefs.update(bad)
    assert prefs.load()["theme"] == "aero"


def test_list_width_is_clamped():
    assert prefs.update({"list_width": 5000})["list_width"] == prefs.LIST_WIDTH_MAX
    assert prefs.update({"list_width": 10})["list_width"] == prefs.LIST_WIDTH_MIN


def test_damaged_file_falls_back_to_defaults():
    p = paths.runtime_dir() / "prefs.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("{not json", encoding="utf-8")
    assert prefs.load()["theme"] == "classic"
    p.write_text(json.dumps({"theme": "pink", "remote_images": True}), encoding="utf-8")
    assert prefs.load() == {**prefs.DEFAULTS, "remote_images": True}


def test_prefs_endpoints(database):
    c = TestClient(create_app(Store(database), TOKEN))
    assert c.get("/prefs").status_code == 401
    r = c.get("/prefs", headers=_auth())
    assert r.status_code == 200 and r.json() == {"prefs": prefs.DEFAULTS, "stored": []}
    r = c.post("/prefs", headers=_auth(), json={"theme": "glass", "classic_mode": "dark"})
    assert r.status_code == 200
    assert r.json()["prefs"]["theme"] == "glass" and r.json()["stored"] == ["classic_mode", "theme"]
    assert c.post("/prefs", headers=_auth(), json={"theme": "pink"}).status_code == 400
    # Second "launch": new app, same data folder.
    c2 = TestClient(create_app(Store(database), TOKEN))
    assert c2.get("/prefs", headers=_auth()).json()["prefs"]["theme"] == "glass"


def test_testserver_host_rejected_outside_tests(database, monkeypatch):
    from api import app as api_app
    monkeypatch.setattr(api_app, "_LOCAL_HOSTS", {"127.0.0.1", "localhost", "[::1]"})
    c = TestClient(create_app(Store(database), TOKEN))
    assert c.get("/accounts", headers=_auth()).status_code == 403
    c2 = TestClient(create_app(Store(database), TOKEN), base_url="http://127.0.0.1")
    assert c2.get("/accounts", headers=_auth()).status_code == 200


def test_invalid_pref_error_carries_a_stable_code(database):
    c = TestClient(create_app(Store(database), TOKEN))
    r = c.post("/prefs", headers=_auth(), json={"language": "klingon"})
    assert r.status_code == 400
    assert r.headers["x-maily-error"] == "invalid_request"
    assert "invalid language" in r.json()["detail"]


def test_language_is_persisted_between_launches(database):
    assert prefs.load()["language"] is None          # first launch: follow the system
    out = prefs.update({"language": "de"})
    assert out["language"] == "de"
    assert json.loads((paths.runtime_dir() / "prefs.json").read_text()) == {"language": "de"}
    c = TestClient(create_app(Store(database), TOKEN))
    assert c.get("/prefs", headers=_auth()).json()["prefs"]["language"] == "de"
    r = c.post("/prefs", headers=_auth(), json={"language": "pt"})
    assert r.status_code == 200 and r.json()["stored"] == ["language"]
    c2 = TestClient(create_app(Store(database), TOKEN))
    assert c2.get("/prefs", headers=_auth()).json()["prefs"]["language"] == "pt"
    # Back to "follow the system".
    assert prefs.update({"language": None})["language"] is None


@pytest.mark.parametrize("code", prefs.LANGUAGES)
def test_every_supported_language_is_accepted(code):
    assert prefs.update({"language": code})["language"] == code


def test_stored_dedsec_theme_migrates_to_zeroday():
    p = paths.runtime_dir() / "prefs.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"theme": "dedsec", "remote_images": True}), encoding="utf-8")
    assert prefs.load()["theme"] == "zeroday"
    # The file itself is rewritten once with the new id, other keys untouched.
    assert json.loads(p.read_text()) == {"theme": "zeroday", "remote_images": True}
    if os.name == "posix":
        assert stat.S_IMODE(p.stat().st_mode) == 0o600
    assert prefs.load()["theme"] == "zeroday"


def test_dedsec_value_posted_by_an_old_client_is_saved_as_zeroday(database):
    # The one-time localStorage migration of the frontend may still post "dedsec".
    c = TestClient(create_app(Store(database), TOKEN))
    r = c.post("/prefs", headers=_auth(), json={"theme": "dedsec"})
    assert r.status_code == 200 and r.json()["prefs"]["theme"] == "zeroday"
    assert json.loads((paths.runtime_dir() / "prefs.json").read_text()) == {"theme": "zeroday"}
