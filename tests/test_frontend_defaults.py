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


def test_splitter_uses_pointer_capture():
    js = (FRONTEND / "app.js").read_text(encoding="utf-8")
    # Redimensionnement uniquement clic maintenu + relachement fiable.
    assert "setPointerCapture" in js and "pointermove" in js


def test_cmd_click_converts_current_mail_to_tab():
    js = (FRONTEND / "app.js").read_text(encoding="utf-8")
    # Le mail courant (ouvert seul) devient un onglet au 1er Cmd+clic.
    assert "!state.tabs.some((t) => t.id === state.currentId)" in js


def test_hover_tooltip_present():
    css = (FRONTEND / "styles.css").read_text(encoding="utf-8")
    assert "[data-tip]:hover::after" in css


def test_glass_light_mode_variant_present():
    css = (FRONTEND / "styles.css").read_text(encoding="utf-8")
    # Le theme Verre s'adapte au mode clair du systeme (texte sombre lisible).
    assert "@media (prefers-color-scheme: light)" in css
