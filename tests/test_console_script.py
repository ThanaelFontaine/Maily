"""`uv run maily` launches the app: console script declared in pyproject.toml."""
import importlib
import importlib.metadata
import pathlib
import shutil
import subprocess
import sys
import tomllib

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _scripts():
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["scripts"]


def test_pyproject_declares_the_maily_console_script():
    assert _scripts() == {"maily": "app.bootstrap:main"}


def test_entry_point_resolves_to_the_bootstrap_main():
    module, func = _scripts()["maily"].split(":")
    assert getattr(importlib.import_module(module), func) is importlib.import_module("app.bootstrap").main


def test_installed_entry_point_matches_pyproject():
    # uv installs the project (build-system declared), so the script exists in the environment.
    eps = [ep for ep in importlib.metadata.entry_points(group="console_scripts") if ep.name == "maily"]
    assert len(eps) == 1 and eps[0].value == "app.bootstrap:main"


def test_console_script_passes_data_dir_then_runs(monkeypatch, tmp_path):
    from app import bootstrap
    from core import paths
    calls = []
    monkeypatch.setattr(bootstrap, "run", lambda: calls.append(paths.runtime_dir()))
    bootstrap.main(["--data-dir", str(tmp_path / "data")])
    assert calls == [tmp_path / "data"]


def test_python_m_app_bootstrap_still_works():
    # --help stops at argument parsing: nothing is launched.
    for cmd in (["-m", "app.bootstrap", "--help"],):
        r = subprocess.run([sys.executable, *cmd], cwd=ROOT, capture_output=True, text=True, timeout=60)
        assert r.returncode == 0 and "usage: maily" in r.stdout and "--data-dir" in r.stdout


def test_maily_executable_answers_help():
    exe = shutil.which("maily", path=str(pathlib.Path(sys.executable).parent))
    assert exe, "the maily console script is installed next to the interpreter"
    r = subprocess.run([exe, "--help"], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0 and "usage: maily" in r.stdout
