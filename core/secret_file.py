"""Magasin de secrets local chiffre (remplace le Trousseau macOS).

Les tokens OAuth, le client OAuth et le token d'API local sont stockes dans un
unique fichier `secrets.enc` (chiffre Fernet/AES) dans le dossier runtime, avec
la cle dans `secrets.key`. Les deux fichiers sont en 0600 (proprietaire seul).

Motivation : dans l'app empaquetee (/Applications/Maily.app), le Trousseau
reclamait le mot de passe a chaque acces car le binaire n'est pas celui qui a
cree les entrees. Un magasin possede par l'app supprime cette invite. L'acces
est protege en amont par Touch ID au lancement (voir core/biometric.py).
"""
from __future__ import annotations
import json
import os
import threading
from cryptography.fernet import Fernet
from core import paths

_LOCK = threading.RLock()


def _key_path():
    return paths.runtime_dir() / "secrets.key"


def _data_path():
    return paths.runtime_dir() / "secrets.enc"


def _load_key() -> bytes:
    p = _key_path()
    if p.exists():
        return p.read_bytes().strip()
    p.parent.mkdir(parents=True, exist_ok=True)
    key = Fernet.generate_key()
    p.write_bytes(key)
    if os.name == "posix":
        os.chmod(p, 0o600)
    return key


def _read_all() -> dict:
    p = _data_path()
    if not p.exists():
        return {}
    try:
        raw = Fernet(_load_key()).decrypt(p.read_bytes())
        return json.loads(raw)
    except Exception:
        return {}


def _write_all(data: dict) -> None:
    p = _data_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    blob = Fernet(_load_key()).encrypt(json.dumps(data).encode("utf-8"))
    p.write_bytes(blob)
    if os.name == "posix":
        os.chmod(p, 0o600)


def get(key: str) -> str | None:
    with _LOCK:
        return _read_all().get(key)


def set(key: str, value: str) -> None:  # noqa: A001 (API deliberee)
    with _LOCK:
        data = _read_all()
        data[key] = value
        _write_all(data)


def delete(key: str) -> None:
    with _LOCK:
        data = _read_all()
        data.pop(key, None)
        _write_all(data)


def migrate_from_keyring(names, service: str = "Maily") -> int:
    """Importe une fois les entrees du Trousseau vers le fichier chiffre.

    Ne demande rien si le processus courant possede deja les entrees (cas du
    lancement en dev via `uv run`, qui les a creees). Best-effort : toute erreur
    (Trousseau indisponible, acces refuse) est ignoree, l'entree restera a
    re-authentifier. N'ecrase jamais une valeur deja presente dans le fichier.
    """
    with _LOCK:
        try:
            import keyring
        except Exception:
            return 0
        data = _read_all()
        migrated = 0
        for name in names:
            if data.get(name) is not None:
                continue
            try:
                v = keyring.get_password(service, name)
            except Exception:
                v = None
            if v is not None:
                data[name] = v
                migrated += 1
        if migrated:
            _write_all(data)
        return migrated
