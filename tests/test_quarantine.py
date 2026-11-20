"""The mark that says a file comes from a mail (core/quarantine.py).

Marked `windows`: the job on a Windows machine of the CI runs these tests (the
ones that need macOS or a POSIX system are skipped there).
"""
import subprocess
import sys

import pytest

from core import quarantine

pytestmark = pytest.mark.windows

mac_only = pytest.mark.skipif(sys.platform != "darwin", reason="macOS only")
win_only = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")


def _file(tmp_path, name="f.bin"):
    p = tmp_path / name
    p.write_bytes(b"data")
    return p


def test_linux_and_others_write_nothing(tmp_path):
    p = _file(tmp_path)
    for platform in ("linux", "freebsd", "cygwin"):
        assert quarantine.mark_from_mail(p, platform=platform) == quarantine.NOT_SUPPORTED
    assert p.read_bytes() == b"data"
    if sys.platform == "darwin":
        r = subprocess.run(["xattr", "-p", "com.apple.quarantine", str(p)],
                           capture_output=True, text=True)
        assert r.returncode != 0


@mac_only
def test_macos_sets_quarantine_properties(tmp_path):
    import Foundation
    p = _file(tmp_path)
    assert quarantine.mark_from_mail(p) == quarantine.APPLIED
    raw = subprocess.run(["xattr", "-p", "com.apple.quarantine", str(p)],
                         capture_output=True, text=True)
    assert raw.returncode == 0 and raw.stdout.count(";") == 3
    # The agent name is not in the raw attribute: the system keeps it with the
    # quarantine event, and gives it back through the same API.
    url = Foundation.NSURL.fileURLWithPath_(str(p))
    ok, props, _ = url.getResourceValue_forKey_error_(
        None, Foundation.NSURLQuarantinePropertiesKey, None)
    names = quarantine.mac_names()
    assert ok
    assert props[names["kLSQuarantineAgentNameKey"]] == "Maily"
    assert props[names["kLSQuarantineTypeKey"]] == names["kLSQuarantineTypeEmailAttachment"]


@mac_only
def test_macos_names_match_the_literals():
    assert quarantine.mac_names() == quarantine._MAC_NAMES


@mac_only
def test_macos_names_fall_back_to_the_literals(monkeypatch):
    import objc
    monkeypatch.setattr(objc, "loadBundleVariables", lambda *a, **k: (_ for _ in ()).throw(RuntimeError))
    assert quarantine.mac_names() == quarantine._MAC_NAMES


@mac_only
def test_macos_ok_false_is_a_failure(tmp_path, monkeypatch):
    """pyobjc returns (ok, error): the pair is always truthy, only ok counts."""
    calls = []

    class FakeURL:
        def setResourceValue_forKey_error_(self, props, key, err):
            calls.append(key)
            return (False, "an error")

    monkeypatch.setattr(quarantine, "_url_for", lambda path: FakeURL())
    with pytest.raises(quarantine.QuarantineFailed):
        quarantine.mark_from_mail(_file(tmp_path))
    assert calls


@mac_only
def test_macos_exception_is_a_failure(tmp_path, monkeypatch):
    def boom(path):
        raise RuntimeError("secret-name.pdf")

    monkeypatch.setattr(quarantine, "_url_for", boom)
    with pytest.raises(quarantine.QuarantineFailed) as e:
        quarantine.mark_from_mail(_file(tmp_path))
    assert "secret-name" not in str(e.value)


def test_foundation_missing_is_a_failure(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "Foundation", None)
    with pytest.raises(quarantine.QuarantineFailed):
        quarantine.mark_from_mail(_file(tmp_path), platform="darwin")


def test_failure_carries_no_path(tmp_path, monkeypatch):
    p = _file(tmp_path, "private-name.pdf")

    def fail(*a, **k):
        raise PermissionError(13, "denied", str(p))

    monkeypatch.setattr("builtins.open", fail)
    monkeypatch.setattr(quarantine, "_windows_volume_has_streams", lambda path: True)
    with pytest.raises(quarantine.QuarantineFailed) as e:
        quarantine.mark_from_mail(p, platform="win32")
    assert e.value.errno == 13
    assert "private-name" not in str(e.value) and "private-name" not in repr(e.value.args)


def test_windows_volume_without_named_streams(tmp_path, monkeypatch):
    p = _file(tmp_path)
    monkeypatch.setattr(quarantine, "_windows_volume_has_streams", lambda path: False)
    assert quarantine.mark_from_mail(p, platform="win32") == quarantine.NOT_SUPPORTED


@win_only
def test_windows_writes_zone_identifier(tmp_path):
    p = _file(tmp_path)
    assert quarantine.mark_from_mail(p) == quarantine.APPLIED
    with open(str(p) + ":Zone.Identifier", "rb") as f:
        assert f.read() == b"[ZoneTransfer]\r\nZoneId=3\r\n"
    assert p.read_bytes() == b"data"
