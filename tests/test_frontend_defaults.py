import pathlib

FRONTEND = pathlib.Path(__file__).resolve().parent.parent / "frontend"
HTML = (FRONTEND / "index.html").read_text(encoding="utf-8")
JS = (FRONTEND / "app.js").read_text(encoding="utf-8")
CSS = (FRONTEND / "styles.css").read_text(encoding="utf-8")


def test_html_default_theme_is_classic():
    assert 'data-theme="classic"' in HTML


def test_js_default_theme_is_classic():
    assert 'const DEFAULT_THEME = "classic";' in JS
    assert '|| "glass"' not in JS and '|| "aero"' not in JS


def test_all_themes_still_selectable():
    for theme in ("classic", "aero", "glass", "dedsec"):
        assert f'data-theme-val="{theme}"' in HTML


def test_theme_button_replaced_by_settings_panel():
    # Plus de bouton « Theme » dans la barre : tout passe par Reglages.
    assert 'id="themebtn"' not in HTML and 'id="thememodal"' not in HTML
    assert 'id="settingsbtn"' in HTML and 'id="settingsmodal"' in HTML
    for pane in ("appearance", "privacy", "accounts", "about"):
        assert f'data-pane="{pane}"' in HTML
    assert 'id="remote-images"' in HTML and 'id="glass-alpha"' in HTML


def test_remote_images_blocked_by_default():
    # Vie privee : images distantes bloquees tant que l'utilisateur ne les active pas.
    assert "remote_images: false" in JS
    assert "PREFS.remote_images === true" in JS
    assert "allow_remote=true\", AUTH" not in JS


def test_prefs_are_stored_server_side_and_migrated():
    # Le port change a chaque lancement : le localStorage ne sert plus qu'a migrer.
    assert 'api("/prefs")' in JS and 'postAction("/prefs"' in JS
    assert "localStorage.setItem" not in JS
    for legacy in ("maily_theme", "maily_classic_mode", "maily_remote_images", "maily_list_width"):
        assert legacy in JS


def test_settings_tabs_follow_aria_tablist_pattern():
    for pane in ("appearance", "privacy", "accounts", "about"):
        assert f'id="tab-{pane}"' in HTML and f'aria-controls="pane-{pane}"' in HTML
        assert f'id="pane-{pane}"' in HTML and f'aria-labelledby="tab-{pane}"' in HTML
    assert "ArrowDown" in JS and "ArrowUp" in JS and "t.tabIndex = on ? 0 : -1" in JS


def test_classic_theme_has_light_and_dark_variants():
    assert ':root[data-theme="classic"]' in CSS
    assert ':root[data-theme="classic"][data-mode="dark"]' in CSS
    assert "@media (prefers-color-scheme: dark)" in CSS


def test_no_hardcoded_timezone():
    assert "Europe/Paris" not in JS


def test_brand_span_removed_from_html():
    assert 'class="brand"' not in HTML


def test_read_dot_collapses_and_realigns():
    # Mail lu : la pastille disparait ET libere sa place (display:none, pas juste
    # transparent) -> fonctionne aussi en DedSec (specificite) et realigne le titre.
    assert ".li-dot.seen { display: none; }" in CSS


def test_splitter_uses_pointer_capture():
    # Redimensionnement uniquement clic maintenu + relachement fiable.
    assert "setPointerCapture" in JS and "pointermove" in JS


def test_cmd_click_converts_current_mail_to_tab():
    # Le mail courant (ouvert seul) devient un onglet au 1er Cmd+clic.
    assert "!state.tabs.some((t) => t.id === state.currentId)" in JS


def test_hover_tooltip_present():
    assert "[data-tip]:hover::after" in CSS


def test_glass_light_mode_variant_present():
    # Le theme Verre s'adapte au mode clair du systeme (texte sombre lisible).
    assert "@media (prefers-color-scheme: light)" in CSS
