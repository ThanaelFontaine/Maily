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
    assert k["background_color"] == "#FFFFFF"


class _FakeWin:
    def __init__(self, uid):
        self.uid = uid


def test_apply_macos_transparency_missing_instance_is_safe():
    # Aucune fenetre native pour cet uid -> ne doit rien lever (et ne rien faire).
    _apply_macos_transparency(_FakeWin("uid-inexistant"))


def test_glass_alpha_persists_to_file(tmp_path, monkeypatch):
    import app.bootstrap as b
    monkeypatch.setattr(b, "_glass_alpha_path", lambda: tmp_path / "glass_alpha")
    assert b.get_glass_alpha() == 0.6            # defaut si fichier absent
    b.set_glass_alpha(0.95)
    assert abs(b.get_glass_alpha() - 0.95) < 1e-6
    b.set_glass_alpha(5)                          # borne haute
    assert b.get_glass_alpha() == 1.0
    b.set_glass_alpha("pas-un-nombre")           # invalide -> inchange
    assert b.get_glass_alpha() == 1.0


def test_apply_macos_transparency_schedules_on_main_thread_when_present(monkeypatch):
    cocoa = pytest.importorskip("webview.platforms.cocoa")
    AppHelper = pytest.importorskip("PyObjCTools.AppHelper")
    import app.bootstrap as b

    b._GLASS_DONE.discard("uid-x")  # garde-fou "une fois par fenetre" : repart propre

    scheduled = []
    monkeypatch.setattr(AppHelper, "callAfter", lambda fn, *a: scheduled.append(fn))

    class _FakeBV:
        webview = object()
        window = object()

    monkeypatch.setitem(cocoa.BrowserView.instances, "uid-x", _FakeBV())
    _apply_macos_transparency(_FakeWin("uid-x"))

    # Le travail natif (re-parentage vibrancy + transparence) est poste sur le thread principal...
    assert len(scheduled) == 1
    # ... et une 2e invocation ne re-planifie pas (re-parentage idempotent).
    _apply_macos_transparency(_FakeWin("uid-x"))
    assert len(scheduled) == 1
