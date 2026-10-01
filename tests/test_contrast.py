"""Legibility: static safeguard (the composer and the settings are themed in
every mode) + live WCAG contrast audit (opt-in)."""
import os
import sys
import subprocess
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
CSS = (ROOT / "frontend" / "styles.css").read_text(encoding="utf-8")


@pytest.mark.parametrize("selector", [
    ':root[data-theme="glass"] .composer',       # readable dark composer in Glassmorphism
    ':root[data-theme="glass"] .composer input',
    ':root[data-theme="glass"] .settingsmenu',
    ':root[data-theme="zeroday"] .composer',
])
def test_theme_scoped_legibility_rules_present(selector):
    # Without these rules, the (light var(--ink)) text lands on a light background: unreadable.
    assert selector in CSS, f"missing legibility rule: {selector}"


@pytest.mark.skipif(
    sys.platform != "darwin" or os.environ.get("MAILY_GUI_TESTS") != "1",
    reason="GUI contrast audit: needs MAILY_GUI_TESTS=1 (macOS + screen).",
)
def test_contrast_audit_passes():
    r = subprocess.run(
        [sys.executable, "scripts/audit_contrast.py"],
        cwd=str(ROOT), env={**os.environ, "PYTHONPATH": str(ROOT)},
        capture_output=True, text=True, timeout=120,
    )
    assert "AUDIT_RESULT: PASS" in r.stdout, r.stdout + "\n" + r.stderr
