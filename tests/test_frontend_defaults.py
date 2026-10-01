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
    for theme in ("classic", "aero", "glass", "zeroday"):
        assert f'data-theme-val="{theme}"' in HTML


def test_theme_button_replaced_by_settings_panel():
    # No more "Theme" button in the top bar: everything goes through Settings.
    assert 'id="themebtn"' not in HTML and 'id="thememodal"' not in HTML
    assert 'id="settingsbtn"' in HTML and 'id="settingsmodal"' in HTML
    for pane in ("appearance", "language", "privacy", "accounts", "about"):
        assert f'data-pane="{pane}"' in HTML
    assert 'id="remote-images"' in HTML and 'id="glass-alpha"' in HTML


def test_remote_images_blocked_by_default():
    # Privacy: remote images stay blocked until the user enables them.
    assert "remote_images: false" in JS
    assert "PREFS.remote_images === true" in JS
    assert "allow_remote=true\", AUTH" not in JS


def test_prefs_are_stored_server_side_and_migrated():
    # The port changes at every launch: localStorage is only used for the migration.
    assert 'api("/prefs")' in JS and 'postAction("/prefs"' in JS
    assert "localStorage.setItem" not in JS
    for legacy in ("maily_theme", "maily_classic_mode", "maily_remote_images", "maily_list_width"):
        assert legacy in JS


def test_settings_tabs_follow_aria_tablist_pattern():
    for pane in ("appearance", "language", "privacy", "accounts", "about"):
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
    # Read message: the dot disappears AND frees its space (display:none, not just
    # transparent), so it also works in Zero Day (specificity) and realigns the title.
    assert ".li-dot.seen { display: none; }" in CSS


def test_splitter_uses_pointer_capture():
    # Resizing only while the button is held + reliable release.
    assert "setPointerCapture" in JS and "pointermove" in JS


def test_cmd_click_converts_current_mail_to_tab():
    # The current message (open on its own) becomes a tab at the first Cmd+click.
    assert "!state.tabs.some((t) => t.id === state.currentId)" in JS


def test_hover_tooltip_present():
    assert "[data-tip]:hover::after" in CSS


def test_glass_light_mode_variant_present():
    # The Glassmorphism theme adapts to the light mode of the system (readable dark text).
    assert "@media (prefers-color-scheme: light)" in CSS


def test_html_language_defaults_to_english():
    assert '<html lang="en"' in HTML


def test_zero_day_theme_has_no_trace_of_its_former_name():
    for text in (HTML, CSS):
        assert "dedsec" not in text.lower() and "watch dogs" not in text.lower()
    assert 'data-theme="zeroday"' in CSS and "Zero Day" in HTML
    # The only mention left in the frontend is the migration of the old id.
    assert JS.lower().count("dedsec") == 1 and 'theme === "dedsec"' in JS


def test_theme_labels_are_in_english():
    assert "Glassmorphism<" in HTML and "Glassmorphisme" not in HTML


def test_no_hardcoded_locale_in_formatting():
    assert "fr-FR" not in JS and "en-US" not in JS
    assert "I18N.locale()" in JS


def test_no_restore_button_for_imap_messages():
    # The engine refuses to restore an IMAP message (untrash_message), so the
    # reading pane offers Restore for Gmail messages only.
    head = JS[JS.index("const isImap"):JS.index("read.appendChild(head)")]
    assert '(isImap ? "" : iconButton("untrashbtn", "restore", "read.restore"))' in head
    assert 'const untrashBtn = head.querySelector("#untrashbtn");\n  if (untrashBtn) {' in JS


def test_engine_refuses_imap_restore(database):
    import pytest
    from core import accounts_service as svc
    from core.store import Store
    store = Store(database)
    aid = store.upsert_account("old@example.net", provider="imap")
    mid = store.upsert_message(aid, "INBOX\x1f1\x1f7", subject="Trashed", is_trashed=1)
    with pytest.raises(ValueError, match="IMAP"):
        svc.untrash_message(store, "old@example.net", mid)
