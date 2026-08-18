"""Lisibilité : garde-fou statique (le composer/les réglages sont bien thémés
dans chaque mode) + audit de contraste WCAG live (opt-in)."""
import os
import sys
import subprocess
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
CSS = (ROOT / "frontend" / "styles.css").read_text(encoding="utf-8")


@pytest.mark.parametrize("selector", [
    ':root[data-theme="glass"] .composer',       # composer sombre lisible en Verre
    ':root[data-theme="glass"] .composer input',
    ':root[data-theme="glass"] .settingsmenu',
    ':root[data-theme="dedsec"] .composer',
])
def test_theme_scoped_legibility_rules_present(selector):
    # Sans ces règles, le texte (var(--ink) clair) tombe sur un fond clair -> illisible.
    assert selector in CSS, f"règle de lisibilité manquante : {selector}"


@pytest.mark.skipif(
    sys.platform != "darwin" or os.environ.get("MAILY_GUI_TESTS") != "1",
    reason="Audit de contraste GUI : MAILY_GUI_TESTS=1 requis (macOS + écran).",
)
def test_contrast_audit_passes():
    r = subprocess.run(
        [sys.executable, "scripts/audit_contrast.py"],
        cwd=str(ROOT), env={**os.environ, "PYTHONPATH": str(ROOT)},
        capture_output=True, text=True, timeout=120,
    )
    assert "AUDIT_RESULT: PASS" in r.stdout, r.stdout + "\n" + r.stderr
