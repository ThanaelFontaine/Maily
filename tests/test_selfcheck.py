"""`Maily --self-check`: the check the CI runs on every built binary."""
import importlib.util
import os
import subprocess
import sys

import pytest

from app import selfcheck


@pytest.mark.skipif(
    sys.platform.startswith("linux") and importlib.util.find_spec("gi") is None,
    reason="the GTK bindings (PyGObject) of the window library are not installed in this Linux environment; "
    "the built Linux app bundles them and the Build workflow runs its self-check",
)
def test_self_check_passes_from_source_and_writes_a_report(tmp_path):
    report = tmp_path / "report.txt"
    before = os.environ.get("MAILY_DATA_DIR")
    assert selfcheck.run(["--report", str(report)]) == 0
    text = report.read_text(encoding="utf-8")
    assert "Self-check passed." in text and "FAIL" not in text
    import core
    assert f"ok   version: {core.__version__}" in text
    # The temporary data folder is not left behind in the environment.
    assert os.environ.get("MAILY_DATA_DIR") == before


def test_a_failing_check_gives_a_non_zero_status(tmp_path, monkeypatch):
    def broken(_data_dir):
        return [("broken", lambda: (_ for _ in ()).throw(RuntimeError("boom")))]

    monkeypatch.setattr(selfcheck, "_checks", broken)
    report = tmp_path / "report.txt"
    assert selfcheck.run(["--report", str(report)]) == 1
    assert "FAIL broken: RuntimeError: boom" in report.read_text(encoding="utf-8")


def test_report_needs_a_file_name():
    assert selfcheck.run(["--report"]) == 2


def test_launcher_prints_its_version():
    import core
    out = subprocess.run([sys.executable, "run_maily.py", "--version"], capture_output=True,
                         text=True, check=True, cwd=os.path.dirname(os.path.dirname(__file__)))
    assert out.stdout.strip() == f"Maily {core.__version__}"


def test_windowed_binary_gets_real_standard_streams(monkeypatch):
    import importlib.util
    import pathlib
    spec = importlib.util.spec_from_file_location(
        "run_maily", pathlib.Path(__file__).resolve().parent.parent / "run_maily.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    mod._ensure_std_streams()
    assert sys.stdout is not None and sys.stdout.isatty() is False
    assert sys.stderr is not None
    sys.stdout.close()
    sys.stderr.close()
