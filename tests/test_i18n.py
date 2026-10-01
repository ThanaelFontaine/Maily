"""Interface translations (frontend/i18n/*.json and frontend/i18n.js).

English is the reference: every language must have exactly its keys, the same
placeholders, and no em or en dash. Every key used by the frontend must exist.
"""
import json
import pathlib
import re

import pytest

FRONTEND = pathlib.Path(__file__).resolve().parent.parent / "frontend"
I18N_DIR = FRONTEND / "i18n"
LANGS = ("en", "fr", "de", "es", "pt")
JS = (FRONTEND / "app.js").read_text(encoding="utf-8")
HTML = (FRONTEND / "index.html").read_text(encoding="utf-8")
I18N_JS = (FRONTEND / "i18n.js").read_text(encoding="utf-8")


def _table(code):
    return json.loads((I18N_DIR / f"{code}.json").read_text(encoding="utf-8"))


EN = _table("en")


def test_exactly_the_five_languages_are_shipped():
    assert sorted(p.stem for p in I18N_DIR.glob("*.json")) == sorted(LANGS)


@pytest.mark.parametrize("code", LANGS[1:])
def test_every_language_has_exactly_the_english_keys(code):
    table = _table(code)
    assert set(table) - set(EN) == set(), "keys unknown to en.json"
    assert set(EN) - set(table) == set(), "keys missing from this language"


@pytest.mark.parametrize("code", LANGS)
def test_values_are_non_empty_strings(code):
    for key, value in _table(code).items():
        assert isinstance(value, str) and value.strip(), key


@pytest.mark.parametrize("code", LANGS[1:])
def test_placeholders_match_english(code):
    table = _table(code)
    for key, value in EN.items():
        assert set(re.findall(r"\{(\w+)\}", table[key])) == set(re.findall(r"\{(\w+)\}", value)), key


@pytest.mark.parametrize("code", LANGS)
def test_no_em_or_en_dash_in_translations(code):
    text = (I18N_DIR / f"{code}.json").read_text(encoding="utf-8")
    assert "\u2014" not in text and "\u2013" not in text


def _used_keys():
    keys = set(re.findall(r'\btr\("([a-zA-Z0-9_.]+)"', JS))
    keys |= set(re.findall(r'data-i18n(?:-[a-z-]+)?="([^"]+)"', HTML))
    keys |= set(re.findall(r'label: "([a-z]+\.[a-zA-Z.]+)"', JS))           # CATEGORIES
    keys |= set(re.findall(r'\["[a-z_]+", "([a-z]+\.[a-zA-Z]+)"\]', JS))    # paintStaticIcons
    keys |= set(re.findall(r'"(toast\.[a-zA-Z]+|composer\.[a-zA-Z]+|imap\.[a-zA-Z]+|read\.[a-zA-Z]+)"', JS))
    return keys


def test_every_key_used_by_the_frontend_exists():
    plural_bases = {k.rsplit(".", 1)[0] for k in EN if k.endswith(".other")}
    # Keys built at run time ("error." + code, "language." + code) are checked below.
    used = {k for k in _used_keys() if not k.endswith(".")}
    missing = {k for k in used if k not in EN and k not in plural_bases}
    assert missing == set()


def test_plural_keys_have_one_and_other():
    for key in EN:
        if key.endswith(".one"):
            assert key[:-4] + ".other" in EN, key


def test_every_api_error_code_is_translated():
    api = (FRONTEND.parent / "api" / "app.py").read_text(encoding="utf-8")
    codes = set(re.findall(r'_fail\(\d+, "([a-z_]+)"', api))
    assert codes and {c for c in codes if f"error.{c}" not in EN} == set()


def test_every_language_name_is_translated():
    for code in LANGS:
        assert f"language.{code}" in EN


def test_native_language_names_are_spelled_correctly():
    names = {code: name for code, name in re.findall(r'code: "(\w+)", name: "([^"]+)"', I18N_JS)}
    decoded = {k: json.loads(f'"{v}"') for k, v in names.items()}   # literal or \\u escapes
    assert decoded == {"en": "English", "fr": "Français", "de": "Deutsch",
                       "es": "Español", "pt": "Português"}


def test_language_list_matches_server_side_preferences():
    from core import prefs
    codes = tuple(re.findall(r'code: "(\w+)", name:', I18N_JS))
    assert codes == prefs.LANGUAGES == LANGS


def test_no_french_left_in_the_frontend_code():
    # Interface text lives in the translation files only.
    for word in ("Réglages", "Écrire", "Envoyer", "Synchroniser", "Corbeille", "Répondre"):
        assert word not in JS and word not in HTML
