#!/usr/bin/env python3
"""Version and release notes for the CI (.github/workflows/release.yml).

  python3 scripts/release_notes.py version          # X.Y.Z from pyproject.toml
  python3 scripts/release_notes.py notes X.Y.Z      # the "## [X.Y.Z]" section of CHANGELOG.md
  python3 scripts/release_notes.py assets X.Y.Z     # the files every release must carry

`notes` exits with status 1 when the section is missing or empty, so that no
release is ever published without notes. Standard library only.
"""
from __future__ import annotations
import pathlib
import re
import sys
import tomllib

ROOT = pathlib.Path(__file__).resolve().parent.parent


def version() -> str:
    v = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    if not re.fullmatch(r"\d+\.\d+\.\d+", v):
        raise SystemExit(f"Invalid version in pyproject.toml: {v} (expected X.Y.Z).")
    return v


# The downloadable builds of a release, each followed by its .sha256 file.
# The release workflow publishes a release only when all of them are attached.
ASSET_PATTERNS = (
    "Maily-{v}-macos-arm64.dmg",
    "Maily-{v}-windows-x64.zip",
    "Maily-{v}-linux-x64.tar.gz",
)


def assets(v: str) -> list[str]:
    """Every file of release v: each build and its checksum file."""
    out = []
    for pattern in ASSET_PATTERNS:
        name = pattern.format(v=v)
        out += [name, name + ".sha256"]
    return out


def notes(v: str, changelog: str | None = None) -> str:
    """Lines between "## [v]" and the next "## [" heading or link reference."""
    text = changelog if changelog is not None else (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    out, on = [], False
    for line in text.splitlines():
        if line.startswith(f"## [{v}]"):
            on = True
            continue
        if on and (line.startswith("## [") or re.match(r"^\[[^\]]+\]: ", line)):
            break
        if on:
            out.append(line)
    return "\n".join(out).strip() + "\n" if any(s.strip() for s in out) else ""


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args == ["version"]:
        print(version())
        return 0
    if len(args) == 2 and args[0] == "notes":
        body = notes(args[1])
        if not body:
            print(f"CHANGELOG.md has no non-empty section for {args[1]}.", file=sys.stderr)
            return 1
        sys.stdout.write(body)
        return 0
    if len(args) == 2 and args[0] == "assets":
        print("\n".join(assets(args[1])))
        return 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
