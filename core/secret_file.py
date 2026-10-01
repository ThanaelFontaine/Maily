"""Magasin de secrets local chiffre.

Les jetons OAuth, le client OAuth, les identifiants IMAP et le jeton de l'API
locale sont ranges dans un unique fichier `secrets.enc` (chiffre avec Fernet :
AES-128-CBC + HMAC-SHA256) dans le dossier de donnees, la cle etant dans
`secrets.key`. Les deux fichiers sont en 0600 (proprietaire seul).

Pourquoi un fichier et pas le Trousseau : dans l'app empaquetee, le Trousseau
macOS reclamait le mot de passe a chaque acces car le binaire n'est pas celui
qui avait cree les entrees. Un magasin possede par l'app supprime cette invite.
Sur macOS, l'app graphique est en plus protegee par Touch ID au lancement
(voir core/biometric.py).

Garanties d'integrite :

- Ecriture atomique : le nouveau contenu part dans un fichier temporaire 0600
  du meme dossier, est force sur le disque (fsync), puis remplace l'ancien d'un
  seul coup (os.replace) ; le dossier est ensuite synchronise. Une coupure en
  plein milieu laisse l'ancien fichier intact, jamais un fichier tronque.
- Verrou inter-processus : l'app, le serveur MCP et les scripts peuvent tourner
  en meme temps. Chaque lecture-modification-ecriture se fait sous un verrou de
  fichier (`secrets.lock`, fcntl.flock sur POSIX, msvcrt.locking sous Windows),
  en plus d'un verrou de fil pour le processus courant. Sans lui, deux ecritures
  concurrentes perdraient l'une des deux mises a jour.
- Cle creee une seule fois, en O_EXCL et 0600 : jamais ecrasee.
- Pas d'effacement silencieux : si `secrets.enc` ne se dechiffre pas (cle
  changee, fichier abime), une SecretStoreError est levee. L'ancien comportement
  (rendre {} en silence) faisait effacer tous les jetons a l'ecriture suivante.
"""
from __future__ import annotations
import contextlib
import json
import os
import pathlib
import tempfile
import threading
import time
from cryptography.fernet import Fernet, InvalidToken
from core import paths

_LOCK = threading.RLock()
_HELD = threading.local()


class SecretStoreError(RuntimeError):
    """Le magasin de secrets est illisible ou incoherent : rien n'est ecrase."""


def _key_path():
    return paths.runtime_dir() / "secrets.key"


def _data_path():
    return paths.runtime_dir() / "secrets.enc"


def _lock_path():
    return paths.runtime_dir() / "secrets.lock"


def _ensure_dir(directory) -> None:
    """Cree le dossier de donnees en 0700 s'il n'existe pas encore.

    Le serveur MCP ou un script peut passer avant l'app : sans cela, le dossier
    serait cree avec l'umask (souvent 0755, lisible par les autres comptes).
    Un dossier deja present n'est pas modifie.
    """
    directory = pathlib.Path(directory)
    if directory.exists():
        return
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name == "posix":
        os.chmod(directory, 0o700)


# ---------------------------------------------------------------------------
# Verrou inter-processus
# ---------------------------------------------------------------------------

def _os_lock(fd) -> None:
    try:
        import fcntl
    except ImportError:  # Windows
        fcntl = None
    if fcntl is not None:
        fcntl.flock(fd, fcntl.LOCK_EX)
        return
    try:
        import msvcrt
    except ImportError:  # plateforme exotique : verrou de fil seulement
        return
    while True:
        try:
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            return
        except OSError:
            time.sleep(0.05)


def _os_unlock(fd) -> None:
    try:
        import fcntl
    except ImportError:
        fcntl = None
    if fcntl is not None:
        fcntl.flock(fd, fcntl.LOCK_UN)
        return
    try:
        import msvcrt
    except ImportError:
        return
    try:
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    except OSError:
        pass


@contextlib.contextmanager
def _locked():
    """Verrou exclusif (fil + processus) autour d'une operation sur le magasin.

    Reentrant dans un meme fil : un appel imbrique ne reprend pas le verrou de
    fichier (flock sur un second descripteur bloquerait le processus lui-meme).
    """
    with _LOCK:
        depth = getattr(_HELD, "depth", 0)
        if depth:
            _HELD.depth = depth + 1
            try:
                yield
            finally:
                _HELD.depth -= 1
            return
        lp = _lock_path()
        _ensure_dir(lp.parent)
        fd = os.open(str(lp), os.O_RDWR | os.O_CREAT, 0o600)
        try:
            _os_lock(fd)
            _HELD.depth = 1
            try:
                yield
            finally:
                _HELD.depth = 0
                _os_unlock(fd)
        finally:
            os.close(fd)


# ---------------------------------------------------------------------------
# Ecritures atomiques
# ---------------------------------------------------------------------------

def _fsync_dir(directory) -> None:
    """Synchronise l'entree de dossier (POSIX) pour que le rename survive a une coupure."""
    if os.name != "posix":
        return
    try:
        dfd = os.open(str(directory), os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(dfd)
    except OSError:
        pass
    finally:
        os.close(dfd)


def _atomic_write(path, blob: bytes) -> None:
    path = pathlib.Path(path)
    _ensure_dir(path.parent)
    # mkstemp cree le fichier en 0600, dans le meme dossier (meme systeme de
    # fichiers : os.replace reste atomique).
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix="." + path.name + ".", suffix=".tmp")
    try:
        if os.name == "posix":
            os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as f:
            fd = None
            f.write(blob)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, str(path))
        tmp = None
        _fsync_dir(path.parent)
    finally:
        if fd is not None:
            os.close(fd)
        if tmp is not None:
            try:
                os.unlink(tmp)
            except OSError:
                pass


def _create_key(p) -> bytes:
    """Cree la cle en O_EXCL + 0600. Si un autre processus l'a creee, la relit."""
    key = Fernet.generate_key()
    try:
        fd = os.open(str(p), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return _read_key(p)
    try:
        if os.name == "posix":
            os.fchmod(fd, 0o600)
        os.write(fd, key)
        os.fsync(fd)
    finally:
        os.close(fd)
    _fsync_dir(p.parent)
    return key


def _read_key(p) -> bytes:
    key = p.read_bytes().strip()
    try:
        Fernet(key)
    except Exception as e:
        raise SecretStoreError(
            f"Cle de chiffrement invalide dans {p}. Le fichier n'a pas ete modifie ; "
            "restaure une sauvegarde de secrets.key ou supprime secrets.key et "
            "secrets.enc pour repartir de zero (les comptes seront a reconnecter)."
        ) from e
    return key


def _load_key(create: bool = True) -> bytes:
    p = _key_path()
    if p.exists():
        return _read_key(p)
    if _data_path().exists():
        # Des secrets existent mais leur cle a disparu : en creer une nouvelle
        # rendrait secrets.enc definitivement illisible, puis l'effacerait.
        raise SecretStoreError(
            f"{p.name} est introuvable alors que {_data_path().name} existe dans {p.parent}. "
            "Rien n'a ete modifie ; restaure secrets.key ou supprime secrets.enc "
            "pour repartir de zero (les comptes seront a reconnecter)."
        )
    if not create:
        raise SecretStoreError(f"{p.name} introuvable dans {p.parent}.")
    _ensure_dir(p.parent)
    return _create_key(p)


def _read_all() -> dict:
    p = _data_path()
    if not p.exists():
        return {}
    key = _load_key(create=False)
    try:
        raw = Fernet(key).decrypt(p.read_bytes())
    except InvalidToken as e:
        raise SecretStoreError(
            f"Impossible de dechiffrer {p} (cle differente ou fichier abime). "
            "Rien n'a ete modifie ; aucun jeton n'a ete efface."
        ) from e
    try:
        data = json.loads(raw)
    except ValueError as e:
        raise SecretStoreError(f"Contenu dechiffre de {p} illisible (JSON invalide).") from e
    if not isinstance(data, dict):
        raise SecretStoreError(f"Contenu dechiffre de {p} inattendu (objet JSON attendu).")
    return data


def _write_all(data: dict) -> None:
    blob = Fernet(_load_key()).encrypt(json.dumps(data).encode("utf-8"))
    _atomic_write(_data_path(), blob)


# ---------------------------------------------------------------------------
# API publique
# ---------------------------------------------------------------------------

def get(key: str) -> str | None:
    with _locked():
        return _read_all().get(key)


def set(key: str, value: str) -> None:  # noqa: A001 (API deliberee)
    with _locked():
        data = _read_all()
        data[key] = value
        _write_all(data)


def delete(key: str) -> None:
    with _locked():
        data = _read_all()
        if key not in data:
            return
        data.pop(key, None)
        _write_all(data)


def migrate_from_keyring(names, service: str = "Maily") -> int:
    """Importe une fois les entrees du Trousseau vers le fichier chiffre.

    Ne demande rien si le processus courant possede deja les entrees (cas du
    lancement en dev via `uv run`, qui les a creees). Best-effort : toute erreur
    du Trousseau (indisponible, acces refuse) est ignoree, l'entree restera a
    re-authentifier. N'ecrase jamais une valeur deja presente dans le fichier.
    Une SecretStoreError (magasin illisible) remonte : on n'ecrit rien dessus.
    """
    with _locked():
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
