"""File names and destinations for the files the MCP tools write to disk.

A file name taken from a mail is untrusted: it is reduced to one safe segment
(safe_filename), the folder must be one of a few user folders
(resolve_destination), and an existing file is never overwritten (write_new).
No dependency, so it can be tested alone.
"""
from __future__ import annotations
import os
import pathlib
import re
import unicodedata

# Folders (under the home folder) where the MCP tools may write.
ALLOWED_ROOTS = ("Downloads", "Desktop", "Documents")

MAX_NAME = 150
MAX_EXT = 16
MAX_SUFFIX = 99
_FORBIDDEN = re.compile(r'[<>:"/\\|?*]')
_RESERVED = re.compile(r"^(CON|PRN|AUX|NUL|CONIN\$|CONOUT\$|COM[0-9¹²³]|LPT[0-9¹²³])$", re.IGNORECASE)


class DestinationNotAllowed(ValueError):
    """The requested folder is outside the folders the tools may write to."""


def _split_ext(name: str) -> tuple[str, str]:
    stem, dot, ext = name.rpartition(".")
    if not dot or not stem or len(ext) + 1 > MAX_EXT:
        return name, ""
    return stem, "." + ext


def safe_filename(name: str | None, default: str = "attachment") -> str:
    """One safe file name segment, whatever the input."""
    if not name:
        return default
    name = unicodedata.normalize("NFC", str(name)).replace("\\", "/")
    name = name.split("/")[-1]
    name = "".join("_" if unicodedata.category(c) in ("Cc", "Cf") else c for c in name)
    name = _FORBIDDEN.sub("_", name)
    name = name.lstrip(".").rstrip(". ")
    if not name:
        return default
    stem, ext = _split_ext(name)
    if _RESERVED.match(stem.split(".")[0].rstrip(" ")):
        stem = "_" + stem
    if len(stem) + len(ext) > MAX_NAME:
        stem = stem[: MAX_NAME - len(ext)]
    name = (stem + ext).rstrip(". ")
    return name or default


def _allowed_roots() -> list[pathlib.Path]:
    home = pathlib.Path.home()
    return [(home / r).resolve() for r in ALLOWED_ROOTS]


def resolve_destination(dest_path: str | None, filename: str) -> tuple[pathlib.Path, str]:
    """(folder, file name) where to write. The folder exists on return and is
    inside one of ALLOWED_ROOTS (links followed); otherwise DestinationNotAllowed."""
    filename = safe_filename(filename)
    if dest_path:
        p = pathlib.Path(dest_path).expanduser()
        if p.is_dir():
            folder = p
        else:
            folder, filename = p.parent, safe_filename(p.name, filename)
    else:
        folder = pathlib.Path.home() / "Downloads"
    folder = folder.resolve()
    if not any(folder == r or folder.is_relative_to(r) for r in _allowed_roots()):
        raise DestinationNotAllowed(
            "the folder must be inside Downloads, Desktop or Documents")
    folder.mkdir(parents=True, exist_ok=True)
    if (folder / filename).resolve().parent != folder:
        raise DestinationNotAllowed("the file name leaves the folder")
    return folder, filename


def write_new(folder: pathlib.Path, filename: str, data: bytes) -> pathlib.Path:
    """Writes data to a new file in folder, 0600, never over an existing file or
    link: a numbered suffix is added on collision."""
    stem, ext = _split_ext(filename)
    for i in range(MAX_SUFFIX + 1):
        path = folder / (filename if i == 0 else f"{stem} ({i}){ext}")
        try:
            with open(path, "xb", opener=lambda p, fl: os.open(p, fl, 0o600)) as f:
                f.write(data)
            return path
        except FileExistsError:
            continue
    raise FileExistsError(f"too many files named {filename!r} in {folder}")
