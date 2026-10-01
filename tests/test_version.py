"""The app version (core.__version__) follows pyproject.toml, the single source
read by the CI to create the tag and the release."""
import pathlib
import re
import tomllib

import core

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _pyproject_version():
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]


def test_core_version_matches_pyproject():
    assert core.__version__ == _pyproject_version()


def test_changelog_has_a_section_for_current_version():
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert re.search(rf"^## \[{re.escape(_pyproject_version())}\]", changelog, re.M)
