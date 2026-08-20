import sys
import pytest
from core import biometric


def test_disabled_env_bypasses(monkeypatch):
    monkeypatch.setenv("MAILY_NO_BIOMETRIC", "1")
    assert biometric.require_unlock() is True


def test_non_darwin_never_gates(monkeypatch):
    monkeypatch.delenv("MAILY_NO_BIOMETRIC", raising=False)
    monkeypatch.setattr(biometric.sys, "platform", "linux")
    assert biometric.require_unlock() is True


def test_missing_framework_does_not_block(monkeypatch):
    monkeypatch.delenv("MAILY_NO_BIOMETRIC", raising=False)
    monkeypatch.setattr(biometric.sys, "platform", "darwin")
    # Simule l'absence du framework LocalAuthentication.
    monkeypatch.setitem(sys.modules, "LocalAuthentication", None)
    assert biometric.require_unlock() is True
