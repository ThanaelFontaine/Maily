import os, stat, sys
from core import paths


def test_runtime_dir_override(tmp_path):
    assert paths.runtime_dir(str(tmp_path)) == tmp_path


def test_runtime_dir_macos(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setenv("HOME", "/Users/tester")
    d = paths.runtime_dir()
    assert str(d) == "/Users/tester/Library/Application Support/Maily"


def test_ensure_runtime_dirs_creates_tree(tmp_path):
    layout = paths.ensure_runtime_dirs(tmp_path / "Maily")
    assert layout["base"].is_dir()
    assert layout["attachments"].is_dir()
    assert layout["logs"].is_dir()
    assert layout["db"].name == "app.sqlite"
    assert layout["runtime_json"].name == "runtime.json"
    if os.name == "posix":
        mode = stat.S_IMODE(layout["base"].stat().st_mode)
        assert mode == 0o700
