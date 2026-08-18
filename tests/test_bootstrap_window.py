from app.bootstrap import window_kwargs


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
