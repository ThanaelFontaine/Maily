"""save_from_mail, write_new(before_write=...) and the extension rule of
dest_path (MAIL-25). Kept apart from test_filenames.py (another lot edits it)."""
import os
import sys

import pytest

from core import filenames, quarantine

pytestmark = pytest.mark.windows

posix_only = pytest.mark.skipif(sys.platform == "win32",
                                reason="a file that is open cannot be replaced on Windows")
win_only = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    return tmp_path.resolve()


@pytest.fixture
def marks(monkeypatch):
    """Replaces the system mark by a spy that records what it saw."""
    seen = []

    def fake(path, platform=None):
        seen.append((path, path.stat().st_size))
        return quarantine.APPLIED

    monkeypatch.setattr(quarantine, "mark_from_mail", fake)
    return seen


def test_save_from_mail_returns_path_and_status(home, marks):
    path, status = filenames.save_from_mail(None, "a.txt", b"hello")
    assert path == home / "Downloads" / "a.txt" and status == "applied"
    assert path.read_bytes() == b"hello"
    assert marks == [(path, 0)]


@win_only
def test_windows_marks_the_file_while_it_is_open_and_keeps_the_data(home):
    """No spy: the real Mark-of-the-Web is written while the file is open."""
    path, status = filenames.save_from_mail(None, "a.txt", b"hello")
    assert status == quarantine.APPLIED
    assert path.read_bytes() == b"hello"
    with open(str(path) + ":Zone.Identifier", "rb") as f:
        assert f.read() == b"[ZoneTransfer]\r\nZoneId=3\r\n"


@win_only
def test_windows_failed_mark_removes_the_open_empty_file(home, monkeypatch):
    def fail(path, platform=None):
        raise quarantine.QuarantineFailed("x")

    monkeypatch.setattr(quarantine, "mark_from_mail", fail)
    with pytest.raises(quarantine.QuarantineFailed):
        filenames.save_from_mail(None, "a.txt", b"hello")
    assert list((home / "Downloads").iterdir()) == []


def test_mark_is_set_before_the_data_is_written(home, marks):
    path, _ = filenames.save_from_mail(None, "a.txt", b"hello")
    assert marks[0][1] == 0 and path.stat().st_size == 5


def test_not_supported_status_is_passed_on(home, monkeypatch):
    monkeypatch.setattr(quarantine, "mark_from_mail",
                        lambda path, platform=None: quarantine.NOT_SUPPORTED)
    assert filenames.save_from_mail(None, "a.txt", b"x")[1] == "not_supported"


def test_failed_mark_leaves_no_file(home, monkeypatch):
    def fail(path, platform=None):
        raise quarantine.QuarantineFailed("x")

    monkeypatch.setattr(quarantine, "mark_from_mail", fail)
    with pytest.raises(quarantine.QuarantineFailed):
        filenames.save_from_mail(None, "a.txt", b"hello")
    assert list((home / "Downloads").iterdir()) == []


@posix_only
def test_a_replaced_file_is_not_removed(home, monkeypatch):
    victim = {}

    def swap(path, platform=None):
        os.unlink(path)
        path.write_bytes(b"")  # a different, empty file at the same path
        victim["p"] = path
        raise quarantine.QuarantineFailed("x")

    monkeypatch.setattr(quarantine, "mark_from_mail", swap)
    with pytest.raises(quarantine.QuarantineFailed):
        filenames.save_from_mail(None, "a.txt", b"hello")
    assert victim["p"].exists()


def test_a_file_that_is_no_longer_empty_is_not_removed(home, monkeypatch):
    def grow(path, platform=None):
        path.write_bytes(b"other")
        raise quarantine.QuarantineFailed("x")

    monkeypatch.setattr(quarantine, "mark_from_mail", grow)
    with pytest.raises(quarantine.QuarantineFailed):
        filenames.save_from_mail(None, "a.txt", b"hello")
    assert (home / "Downloads" / "a.txt").read_bytes() == b"other"


def test_write_new_without_before_write_is_unchanged(tmp_path):
    p = filenames.write_new(tmp_path, "a.txt", b"x")
    assert p.read_bytes() == b"x"
    assert filenames.write_new(tmp_path, "a.txt", b"y").name == "a (1).txt"


def test_before_write_sees_an_empty_file(tmp_path):
    seen = []
    p = filenames.write_new(tmp_path, "a.txt", b"hello",
                            before_write=lambda path, f: seen.append(path.stat().st_size))
    assert seen == [0] and p.read_bytes() == b"hello"


def test_before_write_error_goes_up_and_removes_the_file(tmp_path):
    def boom(path, f):
        raise RuntimeError("no")

    with pytest.raises(RuntimeError):
        filenames.write_new(tmp_path, "a.txt", b"hello", before_write=boom)
    assert list(tmp_path.iterdir()) == []


# --- dest_path cannot change the extension (CA9) ---------------------------


def test_dest_path_cannot_change_the_extension(home):
    with pytest.raises(filenames.DestinationNotAllowed, match="extension"):
        filenames.save_from_mail(str(home / "Desktop" / "x.bat"), "a.txt", b"x")
    assert not (home / "Desktop" / "x.bat").exists()


def test_dest_path_extension_case_is_free(home, marks):
    path, _ = filenames.save_from_mail(str(home / "Desktop" / "x.TXT"), "a.txt", b"x")
    assert path.name == "x.TXT"


def test_dest_path_with_the_same_extension_renames(home, marks):
    path, _ = filenames.save_from_mail(str(home / "Documents" / "renamed.pdf"), "inv.pdf", b"x")
    assert path == home / "Documents" / "renamed.pdf"


def test_a_name_without_extension_gets_none(home):
    with pytest.raises(filenames.DestinationNotAllowed):
        filenames.save_from_mail(str(home / "Desktop" / "x.sh"), "README", b"x")


def test_eml_keeps_its_extension(home, marks):
    with pytest.raises(filenames.DestinationNotAllowed):
        filenames.save_from_mail(str(home / "Desktop" / "x.html"), "msg.eml", b"x")
    path, _ = filenames.save_from_mail(str(home / "Desktop" / "x.eml"), "msg.eml", b"x")
    assert path.suffix == ".eml"


def test_a_folder_as_dest_path_keeps_the_original_name(home, marks):
    (home / "Desktop").mkdir()
    path, _ = filenames.save_from_mail(str(home / "Desktop"), "a.txt", b"x")
    assert path == home / "Desktop" / "a.txt"
