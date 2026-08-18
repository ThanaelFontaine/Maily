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


def test_read_dot_collapses_and_realigns():
    css = (FRONTEND / "styles.css").read_text(encoding="utf-8")
    # Mail lu : la pastille disparait ET libere sa place (display:none, pas juste
    # transparent) -> fonctionne aussi en DedSec (specificite) et realigne le titre.
    assert ".li-dot.seen { display: none; }" in css
