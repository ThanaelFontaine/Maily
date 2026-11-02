import os
import stat
import sys
import pytest

from core import filenames as F


@pytest.mark.parametrize("raw,expected", [
    ("../x", "x"),
    ("../../.zshrc", "zshrc"),
    ("/abs/x", "x"),
    ("..\\x", "x"),
    ("C:\\x\\y", "y"),
    (".", "attachment"),
    ("..", "attachment"),
    ("", "attachment"),
    (None, "attachment"),
    ("a/b/", "attachment"),
])
def test_hostile_names_become_one_segment(raw, expected):
    assert F.safe_filename(raw) == expected


def test_ordinary_unicode_name_is_kept():
    assert F.safe_filename("Facture été.pdf") == "Facture été.pdf"


def test_forbidden_and_control_characters_are_replaced():
    assert F.safe_filename("a:b.txt") == "a_b.txt"
    assert "‮" not in F.safe_filename("fdp‮gnp.exe")
    assert "\x00" not in F.safe_filename("a\x00b.txt")


@pytest.mark.parametrize("raw", ["CON", "nul.txt", "com1.log", "LPT9.tar.gz"])
def test_windows_reserved_names_are_prefixed(raw):
    assert F.safe_filename(raw).startswith("_")


def test_trailing_dot_and_space_removed():
    assert F.safe_filename("x. ") == "x"


def test_long_name_is_cut_and_keeps_extension():
    n = F.safe_filename("a" * 300 + ".pdf")
    assert len(n) <= F.MAX_NAME and n.endswith(".pdf")


def test_write_new_never_overwrites(tmp_path):
    a = F.write_new(tmp_path, "f.txt", b"1")
    b = F.write_new(tmp_path, "f.txt", b"2")
    c = F.write_new(tmp_path, "f.txt", b"3")
    assert [p.name for p in (a, b, c)] == ["f.txt", "f (1).txt", "f (2).txt"]
    assert a.read_bytes() == b"1"


def test_write_new_binary_exact(tmp_path):
    data = b"a\r\nb\x00c\n"
    assert F.write_new(tmp_path, "b.bin", data).read_bytes() == data


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX modes and links")
def test_write_new_mode_0600_and_does_not_follow_links(tmp_path):
    victim = tmp_path / "victim"
    victim.write_text("keep")
    (tmp_path / "f.txt").symlink_to(victim)
    p = F.write_new(tmp_path, "f.txt", b"x")
    assert p.name == "f (1).txt" and victim.read_text() == "keep"
    assert stat.S_IMODE(os.stat(p).st_mode) == 0o600


def test_write_new_gives_up_after_many_collisions(tmp_path):
    for i in range(F.MAX_SUFFIX + 1):
        F.write_new(tmp_path, "f.txt", b"")
    with pytest.raises(FileExistsError):
        F.write_new(tmp_path, "f.txt", b"")


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    return tmp_path.resolve()


def test_default_destination_is_downloads(home):
    folder, name = F.resolve_destination(None, "../x")
    assert folder == home / "Downloads" and name == "x"


def test_existing_allowed_folder(home):
    (home / "Desktop").mkdir()
    folder, name = F.resolve_destination(str(home / "Desktop"), "f.pdf")
    assert folder == home / "Desktop" and name == "f.pdf"


def test_new_nested_path_in_documents_is_created(home):
    folder, name = F.resolve_destination("~/Documents/sous/dossier", "f.pdf")
    assert folder == home / "Documents" / "sous" and folder.is_dir() and name == "dossier"


def test_file_path_inside_downloads(home):
    folder, name = F.resolve_destination("~/Downloads/x.pdf", "other")
    assert folder == home / "Downloads" and name == "x.pdf"


@pytest.mark.parametrize("dest", [
    "~/Library/LaunchAgents", "/tmp", "~/.config/autostart/x.desktop",
    "~/Downloads/../.ssh", "~",
])
def test_forbidden_destinations(home, dest):
    with pytest.raises(F.DestinationNotAllowed):
        F.resolve_destination(dest, "f")
    assert not (home / ".ssh").exists() and not (home / "Library").exists()


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks")
def test_symlink_out_of_allowed_roots_is_refused(home):
    (home / "Downloads").mkdir()
    (home / "Downloads" / "sortie").symlink_to(home)
    with pytest.raises(F.DestinationNotAllowed):
        F.resolve_destination("~/Downloads/sortie", "f")
