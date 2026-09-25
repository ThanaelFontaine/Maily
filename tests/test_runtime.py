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


def test_runtime_file_porte_la_cle_en_0600(tmp_path):
    p = tmp_path / "runtime.json"
    data = runtime.write_runtime_file(p, "127.0.0.1", 50123, token="abc")
    assert data["token"] == "abc"
    lu = runtime.read_runtime_file(p)
    assert lu["token"] == "abc" and lu["port"] == 50123 and lu["host"] == "127.0.0.1"
    assert stat.S_IMODE(p.stat().st_mode) == 0o600


def test_runtime_file_fixes_loose_permissions(tmp_path):
    # Pre-create file with loose permissions (simulates old Maily runtime.json).
    p = tmp_path / "runtime.json"
    p.write_text('{"old": "data"}')
    os.chmod(p, 0o644)
    assert stat.S_IMODE(p.stat().st_mode) == 0o644
    # write_runtime_file should fix permissions before writing token.
    data = runtime.write_runtime_file(p, "127.0.0.1", 50123, token="xyz")
    assert data["token"] == "xyz"
    # Verify permissions are fixed to 0o600.
    assert stat.S_IMODE(p.stat().st_mode) == 0o600
    lu = runtime.read_runtime_file(p)
    assert lu["token"] == "xyz"


def test_runtime_file_no_fd_leak_on_fchmod_error(tmp_path, monkeypatch):
    # Verify fd is closed if os.fchmod raises (fd leak protection).
    p = tmp_path / "runtime.json"
    fd_count_before = len(os.listdir("/dev/fd")) if os.path.exists("/dev/fd") else -1

    def raise_on_fchmod(fd, mode):
        raise OSError("test error from fchmod")

    monkeypatch.setattr("os.fchmod", raise_on_fchmod)
    with pytest.raises(OSError, match="test error from fchmod"):
        runtime.write_runtime_file(p, "127.0.0.1", 50123, token="abc")

    # Verify fd was closed (no leak): /dev/fd count should be same.
    if os.path.exists("/dev/fd"):
        fd_count_after = len(os.listdir("/dev/fd"))
        assert fd_count_after == fd_count_before, "fd leak detected"
