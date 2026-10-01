"""Release pipeline: notes taken from CHANGELOG.md, and a workflow that never
publishes a release without its macOS app."""
import importlib.util
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
WORKFLOW = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")


def _rn():
    spec = importlib.util.spec_from_file_location("release_notes", ROOT / "scripts" / "release_notes.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _job(name):
    m = re.search(rf"^  {name}:\n(.*?)(?=^  [a-z][a-z-]*:\n|\Z)", WORKFLOW, re.M | re.S)
    assert m, f"job {name} missing"
    return m.group(1)


def test_version_matches_pyproject_and_core():
    import core
    assert _rn().version() == core.__version__


def test_notes_of_the_current_version_are_not_empty():
    rn = _rn()
    body = rn.notes(rn.version())
    assert body.strip() and not body.startswith("## [")


def test_notes_stop_at_the_next_section_and_at_link_references():
    text = "# Changelog\n\n## [Unreleased]\n\n## [1.2.0] - 2026-01-01\n\nNew.\n\n## [1.1.0] - 2025-01-01\n\nOld.\n"
    assert _rn().notes("1.2.0", text) == "New.\n"
    text2 = "## [1.2.0]\n\nOnly.\n\n[1.2.0]: https://example.com/compare\n"
    assert _rn().notes("1.2.0", text2) == "Only.\n"


@pytest.mark.parametrize("text", ["## [1.2.0]\n\n\n## [1.1.0]\nOld.\n", "## [1.1.0]\nOld.\n"])
def test_missing_or_empty_notes_fail(text, monkeypatch, capsys):
    rn = _rn()
    assert rn.notes("1.2.0", text) == ""
    monkeypatch.setattr(rn, "notes", lambda v: "")
    assert rn.main(["notes", "1.2.0"]) == 1


def test_jobs_run_build_before_publish():
    assert re.search(r"^  plan:\n", WORKFLOW, re.M)
    assert "needs: plan" in _job("build")
    assert "needs: [plan, build]" in _job("publish")


def test_build_job_publishes_nothing_and_checks_arm64():
    build = _job("build")
    assert "gh release" not in build and "git push" not in build and "git tag" not in build
    assert "runs-on: macos-latest" in build
    assert 'lipo -archs "$APP/Contents/MacOS/Maily"' in build and '!= "arm64"' in build
    assert "CFBundleShortVersionString" in build
    assert "actions/upload-artifact@" in build


def test_publish_creates_a_draft_with_the_files_then_publishes_it():
    publish = _job("publish")
    assert "actions/download-artifact@" in publish
    assert "shasum -a 256 -c" in publish
    create = publish.index("gh release create")
    assert "--draft --verify-tag" in publish[create:create + 300]
    assert publish.index("git push origin") < create < publish.index("gh release edit \"$TAG\" --draft=false")


def test_no_clobber_anywhere():
    assert "--clobber" not in WORKFLOW


def test_reruns_recover():
    publish = _job("publish")
    # an existing tag on the same commit is reused, a leftover draft is replaced
    assert 'git rev-list -n 1 "$TAG"' in publish and "$HEAD_SHA" in publish
    assert "releases/$ID" in publish and '"$DRAFT" = "true"' in publish
    # only an explicit "nothing to do" from plan skips the next jobs
    assert "needs.plan.outputs.needed != 'false'" in _job("build")
    assert "needs.plan.outputs.needed != 'false'" in publish
