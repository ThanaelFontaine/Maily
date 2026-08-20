import os, stat
import pytest
from core import runtime


@pytest.fixture(autouse=True)
def tmp_secret_store(monkeypatch, tmp_path):
    from core import secret_file
    monkeypatch.setattr(secret_file.paths, "runtime_dir", lambda override=None: tmp_path)
    return tmp_path


def test_token_is_stable():
    t1 = runtime.get_or_create_api_token()
    t2 = runtime.get_or_create_api_token()
    assert t1 == t2 and len(t1) >= 20


def test_runtime_file_roundtrip(tmp_path):
    p = tmp_path / "runtime.json"
    out = runtime.write_runtime_file(p, "127.0.0.1", 54321)
    assert out["port"] == 54321
    assert out["base_url"] == "http://127.0.0.1:54321"
    data = runtime.read_runtime_file(p)
    assert data["base_url"] == "http://127.0.0.1:54321"
    assert "token" not in data
    if os.name == "posix":
        assert stat.S_IMODE(p.stat().st_mode) == 0o600
