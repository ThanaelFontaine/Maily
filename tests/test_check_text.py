"""scripts/check_text.py: no em or en dash, no personal path or address."""
import importlib.util
import pathlib
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
EM, EN = chr(0x2014), chr(0x2013)
NO_LOCAL = {"CHECK_TEXT_LOCAL": "/nonexistent/patterns"}


def _ct():
    spec = importlib.util.spec_from_file_location("check_text", ROOT / "scripts" / "check_text.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def repo(tmp_path):
    def make(files):
        subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
        for name, content in files.items():
            path = tmp_path / name
            path.parent.mkdir(parents=True, exist_ok=True)
            data = content if isinstance(content, bytes) else content.encode("utf-8")
            path.write_bytes(data)
        subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
        return tmp_path
    return make


def test_dashes_are_found_with_their_line_number():
    assert _ct().find_dashes(f"fine\na {EM} b\nfine\nc {EN} d") == [2, 4]
    assert _ct().find_dashes("a - b, c: d") == []


def test_personal_path_and_address_are_found():
    ct = _ct()
    assert ct.find_patterns("README.md", "see /Users/alice/x", ct.GENERIC_PATTERNS)[0][0] == 1
    assert ct.find_patterns("README.md", "ok\nsee /home/bob", ct.GENERIC_PATTERNS)[0][0] == 2
    assert ct.find_patterns("README.md", "write alice@gmail.com", ct.GENERIC_PATTERNS)
    assert ct.find_patterns("README.md", "write bob@icloud.com", ct.GENERIC_PATTERNS)


def test_a_bare_provider_domain_is_fine():
    ct = _ct()
    assert not ct.find_patterns("README.md", "a regular @gmail.com address", ct.GENERIC_PATTERNS)
    assert not ct.find_patterns("README.md", "user@example.com", ct.GENERIC_PATTERNS)


def test_allowed_files_may_quote_their_own_pattern_only():
    ct = _ct()
    fake_home = "/Users/tester/Library"
    assert not ct.find_patterns("tests/test_paths.py", fake_home, ct.GENERIC_PATTERNS)
    assert ct.find_patterns("tests/test_other.py", fake_home, ct.GENERIC_PATTERNS)
    # The exception is for the home folder only, not for an address.
    assert ct.find_patterns("tests/test_paths.py", "alice@gmail.com", ct.GENERIC_PATTERNS)


def test_clean_repository_passes(repo, capsys):
    root = repo({"a.md": "plain text, with a hyphen - and a colon: ok\n"})
    assert _ct().main(root, NO_LOCAL) == 0
    out = capsys.readouterr().out
    assert "check-text ok (1 files)" in out and "generic patterns only" in out


def test_a_dash_fails_the_check_and_names_file_and_line(repo, capsys):
    root = repo({"docs/a.md": f"one\ntwo {EM} three\n"})
    assert _ct().main(root, NO_LOCAL) == 1
    out = capsys.readouterr().out
    assert "docs/a.md:2: em or en dash" in out and "failed: 1 hit(s)" in out


def test_binary_and_unreadable_files_are_skipped(repo, capsys):
    root = repo({"logo.png": f"{EM}".encode(), "blob.bin": b"\xff\xfe\x00 /Users/alice", "a.md": "ok\n"})
    assert _ct().main(root, NO_LOCAL) == 0
    assert "check-text ok (1 files)" in capsys.readouterr().out


def test_local_patterns_are_read_from_the_named_file(repo, tmp_path_factory, capsys):
    root = repo({"a.md": "the secret-project plan\n"})
    local = tmp_path_factory.mktemp("local") / "patterns"
    local.write_text("# a comment\n\nsecret-project\n", encoding="utf-8")
    assert _ct().main(root, {"CHECK_TEXT_LOCAL": str(local)}) == 1
    out = capsys.readouterr().out
    assert "private patterns loaded" in out and "a.md:1: private path or address" in out
    assert _ct().main(root, NO_LOCAL) == 0


def test_the_repository_itself_passes(capsys):
    assert _ct().main(ROOT, NO_LOCAL) == 0
    assert "check-text ok" in capsys.readouterr().out
