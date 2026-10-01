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
    assert prefs.load() == {"theme": "classic", "classic_mode": "auto", "remote_images": False, "list_width": None}
    assert prefs.stored_keys() == set()


def test_update_persists_in_data_dir_with_owner_only_perms():
    out = prefs.update({"theme": "dedsec", "remote_images": True})
    assert out["theme"] == "dedsec" and out["remote_images"] is True
    p = paths.runtime_dir() / "prefs.json"
    assert json.loads(p.read_text()) == {"remote_images": True, "theme": "dedsec"}
    if os.name == "posix":
        assert stat.S_IMODE(p.stat().st_mode) == 0o600
    # Un « nouveau lancement » relit le fichier : rien ne depend du port ni de la webview.
    assert prefs.load()["theme"] == "dedsec"
    assert prefs.stored_keys() == {"theme", "remote_images"}


@pytest.mark.parametrize("bad", [
    {"theme": "rose"}, {"classic_mode": "nuit"}, {"remote_images": "oui"},
    {"list_width": "large"}, {"inconnue": 1}, ["theme"],
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
    p.write_text("{pas du json", encoding="utf-8")
    assert prefs.load()["theme"] == "classic"
    p.write_text(json.dumps({"theme": "rose", "remote_images": True}), encoding="utf-8")
    assert prefs.load() == {**prefs.DEFAULTS, "remote_images": True}


def test_prefs_endpoints(database):
    c = TestClient(create_app(Store(database), TOKEN))
    assert c.get("/prefs").status_code == 401
    r = c.get("/prefs", headers=_auth())
    assert r.status_code == 200 and r.json() == {"prefs": prefs.DEFAULTS, "stored": []}
    r = c.post("/prefs", headers=_auth(), json={"theme": "glass", "classic_mode": "dark"})
    assert r.status_code == 200
    assert r.json()["prefs"]["theme"] == "glass" and r.json()["stored"] == ["classic_mode", "theme"]
    assert c.post("/prefs", headers=_auth(), json={"theme": "rose"}).status_code == 400
    # Second « lancement » : nouvelle app, meme dossier de donnees.
    c2 = TestClient(create_app(Store(database), TOKEN))
    assert c2.get("/prefs", headers=_auth()).json()["prefs"]["theme"] == "glass"


def test_testserver_host_rejected_outside_tests(database, monkeypatch):
    from api import app as api_app
    monkeypatch.setattr(api_app, "_LOCAL_HOSTS", {"127.0.0.1", "localhost", "[::1]"})
    c = TestClient(create_app(Store(database), TOKEN))
    assert c.get("/accounts", headers=_auth()).status_code == 403
    c2 = TestClient(create_app(Store(database), TOKEN), base_url="http://127.0.0.1")
    assert c2.get("/accounts", headers=_auth()).status_code == 200
