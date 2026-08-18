import pathlib

FRONTEND = pathlib.Path(__file__).resolve().parent.parent / "frontend"


def test_html_default_theme_is_glass():
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")
    assert 'data-theme="glass"' in html


def test_brand_span_removed_from_html():
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")
    assert 'class="brand"' not in html


def test_js_default_theme_is_glass():
    js = (FRONTEND / "app.js").read_text(encoding="utf-8")
    assert '|| "glass"' in js
    assert '|| "aero"' not in js
