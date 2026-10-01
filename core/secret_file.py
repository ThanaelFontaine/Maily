"""Local encrypted secret store.

OAuth tokens, the OAuth client, IMAP credentials and the local API token are
kept in a single `secrets.enc` file (encrypted with Fernet: AES-128-CBC +
HMAC-SHA256) in the data folder, the key being in `secrets.key`. Both files
are 0600 (owner only).

Why a file and not the Keychain: in the packaged app, the macOS Keychain asked
for the password at every access because the binary was not the one that had
created the entries. A store owned by the app removes that prompt. On macOS,
the desktop app is also protected by Touch ID at launch (see core/biometric.py).

Integrity guarantees:

- Atomic writes: the new content goes to a temporary 0600 file in the same
  folder, is forced to disk (fsync), then replaces the old one in one step
  (os.replace); the folder is then synced. A power cut in the middle leaves the
  old file intact, never a truncated file.
- Inter-process lock: the app, the MCP server and scripts may run at the same
  time. Every read-modify-write happens under a file lock (`secrets.lock`,
  fcntl.flock on POSIX, msvcrt.locking on Windows), plus a thread lock for the
  current process. Without it, two concurrent writes would lose one of the two
  updates.
- Key created once, with O_EXCL and 0600: never overwritten.
- No silent erasure: if `secrets.enc` cannot be decrypted (changed key,
  damaged file), a SecretStoreError is raised. The old behavior (silently
  returning {}) made the next write erase every token.
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
    """The secret store is unreadable or inconsistent: nothing is overwritten."""


def _key_path():
    return paths.runtime_dir() / "secrets.key"


def _data_path():
    return paths.runtime_dir() / "secrets.enc"


def _lock_path():
    return paths.runtime_dir() / "secrets.lock"


def _ensure_dir(directory) -> None:
    """Creates the data folder with mode 0700 if it does not exist yet.

    The MCP server or a script may run before the app: without this, the folder
    would be created with the umask (often 0755, readable by other accounts).
    An existing folder is left unchanged.
    """
    directory = pathlib.Path(directory)
    if directory.exists():
        return
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name == "posix":
        os.chmod(directory, 0o700)


# ---------------------------------------------------------------------------
# Inter-process lock
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
    except ImportError:  # unusual platform: thread lock only
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
    """Exclusive lock (thread + process) around an operation on the store.

    Reentrant within a thread: a nested call does not take the file lock again
    (flock on a second descriptor would block the process itself).
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
# Atomic writes
# ---------------------------------------------------------------------------

def _fsync_dir(directory) -> None:
    """Syncs the directory entry (POSIX) so that the rename survives a power cut."""
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
    # mkstemp creates the file with mode 0600, in the same folder (same file
    # system: os.replace stays atomic).
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
    """Creates the key with O_EXCL + 0600. If another process created it, reads it back."""
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
            f"Invalid encryption key in {p}. The file was not changed; "
            "restore a backup of secrets.key, or delete secrets.key and "
            "secrets.enc to start from scratch (accounts will have to be connected again)."
        ) from e
    return key


def _load_key(create: bool = True) -> bytes:
    p = _key_path()
    if p.exists():
        return _read_key(p)
    if _data_path().exists():
        # Secrets exist but their key is gone: creating a new one would make
        # secrets.enc permanently unreadable, then erase it.
        raise SecretStoreError(
            f"{p.name} is missing while {_data_path().name} exists in {p.parent}. "
            "Nothing was changed; restore secrets.key, or delete secrets.enc "
            "to start from scratch (accounts will have to be connected again)."
        )
    if not create:
        raise SecretStoreError(f"{p.name} not found in {p.parent}.")
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
            f"Cannot decrypt {p} (different key or damaged file). "
            "Nothing was changed; no token was erased."
        ) from e
    try:
        data = json.loads(raw)
    except ValueError as e:
        raise SecretStoreError(f"Decrypted content of {p} is unreadable (invalid JSON).") from e
    if not isinstance(data, dict):
        raise SecretStoreError(f"Unexpected decrypted content of {p} (a JSON object is expected).")
    return data


def _write_all(data: dict) -> None:
    blob = Fernet(_load_key()).encrypt(json.dumps(data).encode("utf-8"))
    _atomic_write(_data_path(), blob)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get(key: str) -> str | None:
    with _locked():
        return _read_all().get(key)


def set(key: str, value: str) -> None:  # noqa: A001 (deliberate API)
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
    """Imports the Keychain entries into the encrypted file, once.

    Asks for nothing if the current process already owns the entries (the case
    of a dev launch through `uv run`, which created them). Best effort: any
    Keychain error (unavailable, access denied) is ignored, and the entry will
    need a new sign-in. Never overwrites a value already in the file. A
    SecretStoreError (unreadable store) is raised: nothing is written on it.
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
