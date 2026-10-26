#!/usr/bin/env python3
"""Text check for the repository (job "check-text" of .github/workflows/tests.yml).

  python3 scripts/check_text.py

Every tracked text file is checked for:
  - an em dash or an en dash (use a colon, a comma, parentheses or a hyphen);
  - a personal path or address: /Users/<name>, /home/<name>, or a full
    gmail.com, icloud.com or outlook address (a bare "@gmail.com" is fine).

The maintainer's own private patterns (one regular expression per line, "#"
for comments) are read from the file named by CHECK_TEXT_LOCAL, or else from
~/.config/check-text/patterns. They never live in the repository, so the CI
and a contributor only run the generic patterns.

Prints "check-text ok (N files)" and exits 0, or lists every hit and exits 1.
Standard library only, Python 3.9 or later.
"""
from __future__ import annotations
import os
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent

# Built from code points so that this file holds no dash itself.
DASHES = (chr(0x2014), chr(0x2013))

GENERIC_PATTERNS = (
    r"/Users/[A-Za-z]",
    r"/home/[a-z]",
    r"[A-Za-z0-9._%+-]+@(gmail\.com|icloud\.com|outlook\.)",
)

# Files that quote a generic pattern on purpose: the checker, its test, and a
# test that needs a fake user folder.
ALLOWED = {
    "scripts/check_text.py": GENERIC_PATTERNS,
    "tests/test_check_text.py": GENERIC_PATTERNS,
    "tests/test_paths.py": (r"/Users/[A-Za-z]",),
}

BINARY_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".icns", ".pdf",
    ".woff", ".woff2", ".ttf", ".otf",
}


def find_dashes(text: str) -> list[int]:
    """Line numbers (1 based) that contain an em dash or an en dash."""
    return [i for i, line in enumerate(text.split("\n"), 1) if any(d in line for d in DASHES)]


def find_patterns(file: str, text: str, patterns) -> list[tuple[int, str]]:
    """(line, pattern) for each line that matches a pattern not allowed in this file."""
    allowed = ALLOWED.get(file, ())
    active = [re.compile(p) for p in patterns if p not in allowed]
    return [
        (i, rx.pattern)
        for i, line in enumerate(text.split("\n"), 1)
        for rx in active
        if rx.search(line)
    ]


def local_patterns(environ=os.environ) -> list[str] | None:
    """The maintainer's private patterns, or None when there is no such file."""
    name = environ.get("CHECK_TEXT_LOCAL")
    path = pathlib.Path(name) if name else pathlib.Path.home() / ".config" / "check-text" / "patterns"
    if not path.is_file():
        return None
    lines = (line.strip() for line in path.read_text(encoding="utf-8").splitlines())
    return [line for line in lines if line and not line.startswith("#")]


def tracked_files(root: pathlib.Path) -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "-z"], cwd=root, check=True, capture_output=True, text=True
    ).stdout
    return [f for f in out.split("\0") if f]


def main(root: pathlib.Path = ROOT, environ=os.environ) -> int:
    local = local_patterns(environ)
    patterns = list(GENERIC_PATTERNS) + (local or [])
    print("check-text: private patterns loaded" if local is not None else "check-text: generic patterns only")
    hits, checked = [], 0
    for file in tracked_files(root):
        path = root / file
        if path.suffix.lower() in BINARY_EXTENSIONS or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        checked += 1
        hits += [f"{file}:{n}: em or en dash" for n in find_dashes(text)]
        hits += [f"{file}:{n}: private path or address ({p})" for n, p in find_patterns(file, text, patterns)]
    for hit in hits:
        print(hit)
    print(f"check-text failed: {len(hits)} hit(s)" if hits else f"check-text ok ({checked} files)")
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
