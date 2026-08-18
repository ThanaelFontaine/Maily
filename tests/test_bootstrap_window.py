import pytest

from app.bootstrap import window_kwargs, _apply_macos_transparency


def test_macos_transparent_and_vibrancy():
    k = window_kwargs("darwin")
    assert k["transparent"] is True
    assert k["vibrancy"] is True
    assert k["width"] == 1240 and k["height"] == 820


def test_linux_transparent_without_vibrancy():
    k = window_kwargs("linux")
    assert k["transparent"] is True
    assert "vibrancy" not in k


def test_windows_opaque_with_fallback_background():
    k = window_kwargs("win32")
    assert "transparent" not in k
    assert "vibrancy" not in k
    assert k["background_color"] == "#EDF0FB"


class _FakeWin:
    def __init__(self, uid):
        self.uid = uid


def test_apply_macos_transparency_missing_instance_is_safe():
    # Aucune fenetre native pour cet uid -> ne doit rien lever (et ne rien faire).
    _apply_macos_transparency(_FakeWin("uid-inexistant"))


def test_apply_macos_transparency_sets_clear_when_instance_present(monkeypatch):
    cocoa = pytest.importorskip("webview.platforms.cocoa")
    from PyObjCTools import AppHelper

    captured = []

    class _FakeWebview:
        def setUnderPageBackgroundColor_(self, color):
            captured.append(color)

    class _FakeBV:
        webview = _FakeWebview()

    monkeypatch.setitem(cocoa.BrowserView.instances, "uid-x", _FakeBV())
    # Execute le callback tout de suite au lieu de le poster sur la run loop.
    monkeypatch.setattr(AppHelper, "callAfter", lambda fn, *a: fn(*a))

    _apply_macos_transparency(_FakeWin("uid-x"))

    assert len(captured) == 1  # underPageBackgroundColor force en clair
    assert captured[0].alphaComponent() == 0.0
