"""Preferences de l'interface, rangees cote serveur dans `prefs.json`.

Pourquoi pas le localStorage de la webview : l'API locale ecoute sur un port
aleatoire, donc l'origine de la page (http://127.0.0.1:<port>) change a chaque
lancement et son localStorage repart vide ; en plus, sur macOS, pywebview
ignore `storage_path`. Les choix (theme, mode Classic, images distantes,
largeur de la liste) vivent donc dans le dossier de donnees, comme la densite
du verre.

Le fichier est cree en 0600 et reecrit de facon atomique. Seules les cles
connues sont acceptees, avec des valeurs validees : une valeur inattendue ou un
fichier abime retombe sur les valeurs par defaut, jamais sur une erreur au
demarrage.
"""
from __future__ import annotations
import json
import os
import tempfile
import threading
from core import paths

_LOCK = threading.Lock()

THEMES = ("classic", "aero", "glass", "dedsec")
CLASSIC_MODES = ("auto", "light", "dark")
LIST_WIDTH_MIN, LIST_WIDTH_MAX = 260, 720

DEFAULTS = {
    "theme": "classic",
    "classic_mode": "auto",
    "remote_images": False,
    "list_width": None,
}


class InvalidPref(ValueError):
    """Cle inconnue ou valeur invalide dans une mise a jour de preferences."""


def _path():
    return paths.runtime_dir() / "prefs.json"


def _validate(key, value):
    if key == "theme":
        if value not in THEMES:
            raise InvalidPref(f"theme invalide : {value!r}")
        return value
    if key == "classic_mode":
        if value not in CLASSIC_MODES:
            raise InvalidPref(f"classic_mode invalide : {value!r}")
        return value
    if key == "remote_images":
        if not isinstance(value, bool):
            raise InvalidPref("remote_images doit etre un booleen")
        return value
    if key == "list_width":
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise InvalidPref("list_width doit etre un nombre")
        return int(max(LIST_WIDTH_MIN, min(LIST_WIDTH_MAX, value)))
    raise InvalidPref(f"preference inconnue : {key!r}")


def load() -> dict:
    """Preferences completes (valeurs par defaut pour ce qui manque ou est invalide)."""
    out = dict(DEFAULTS)
    try:
        raw = json.loads(_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return out
    if not isinstance(raw, dict):
        return out
    for key, value in raw.items():
        if key in DEFAULTS:
            try:
                out[key] = _validate(key, value)
            except InvalidPref:
                pass
    return out


def stored_keys() -> set:
    """Cles effectivement enregistrees (sert a la migration depuis le localStorage)."""
    try:
        raw = json.loads(_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    return {k for k in raw if k in DEFAULTS} if isinstance(raw, dict) else set()


def _write(data: dict) -> None:
    p = _path()
    if not p.parent.exists():
        p.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if os.name == "posix":
            os.chmod(p.parent, 0o700)
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=".prefs.json.", suffix=".tmp")
    try:
        if os.name == "posix":
            os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            fd = None
            json.dump(data, f, indent=2, sort_keys=True)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, str(p))
        tmp = None
    finally:
        if fd is not None:
            os.close(fd)
        if tmp is not None:
            try:
                os.unlink(tmp)
            except OSError:
                pass


def update(changes: dict) -> dict:
    """Valide puis enregistre `changes` (mise a jour partielle). Rend les preferences completes.

    Leve InvalidPref sans rien ecrire si une cle ou une valeur est invalide.
    """
    if not isinstance(changes, dict):
        raise InvalidPref("objet JSON attendu")
    clean = {k: _validate(k, v) for k, v in changes.items()}
    with _LOCK:
        current = {k: v for k, v in load().items() if k in stored_keys()}
        current.update(clean)
        _write(current)
        return load()
