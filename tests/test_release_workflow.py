"""Release pipeline: notes taken from CHANGELOG.md, builds for macOS, Windows
and Linux, and a workflow that never publishes a release without all of them."""
import importlib.util
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
WORKFLOW = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
BUILD = (ROOT / ".github" / "workflows" / "build.yml").read_text(encoding="utf-8")


def _rn():
    spec = importlib.util.spec_from_file_location("release_notes", ROOT / "scripts" / "release_notes.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _job(name, text=WORKFLOW):
    m = re.search(rf"^  {name}:\n(.*?)(?=^  [a-z][a-z-]*:\n|\Z)", text, re.M | re.S)
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


def test_assets_are_the_three_builds_and_their_checksums():
    assert _rn().assets("1.2.3") == [
        "Maily-1.2.3-macos-arm64.dmg", "Maily-1.2.3-macos-arm64.dmg.sha256",
        "Maily-1.2.3-windows-x64.zip", "Maily-1.2.3-windows-x64.zip.sha256",
        "Maily-1.2.3-linux-x64.tar.gz", "Maily-1.2.3-linux-x64.tar.gz.sha256",
        "Maily-macos-arm64.dmg", "Maily-windows-x64.zip", "Maily-linux-x64.tar.gz",
    ]


def test_aliases_copy_each_build_under_a_fixed_name():
    assert _rn().aliases("1.2.3") == [
        ("Maily-macos-arm64.dmg", "Maily-1.2.3-macos-arm64.dmg"),
        ("Maily-windows-x64.zip", "Maily-1.2.3-windows-x64.zip"),
        ("Maily-linux-x64.tar.gz", "Maily-1.2.3-linux-x64.tar.gz"),
    ]
    publish = _job("publish")
    assert "scripts/release_notes.py aliases" in publish
    assert publish.index("release_notes.py aliases") < publish.index("Missing build file")


def test_release_builds_with_the_build_workflow_on_the_tested_commit():
    build = _job("build")
    assert "uses: ./.github/workflows/build.yml" in build
    assert "ref: ${{ github.event.workflow_run.head_sha }}" in build
    assert "workflow_call:" in BUILD


def test_build_workflow_publishes_nothing():
    for word in ("gh release", "git push", "git tag", "contents: write"):
        assert word not in BUILD


def test_macos_build_checks_arm64_runs_the_app_and_makes_the_dmg():
    mac = _job("macos", BUILD)
    assert "runs-on: macos-latest" in mac
    assert 'lipo -archs "$APP/Contents/MacOS/Maily"' in mac and '!= "arm64"' in mac
    assert "CFBundleShortVersionString" in mac
    assert "--self-check --window" in mac
    assert "scripts/build_dmg.sh dist/Maily.app release-assets" in mac
    assert "name: maily-macos-arm64" in mac


def test_windows_and_linux_builds_run_the_binary_before_packaging():
    win = _job("windows", BUILD)
    assert "runs-on: windows-latest" in win and "name: maily-windows-x64" in win
    assert "'--self-check', '--window'" in win
    assert win.index("--self-check") < win.index("7z a")
    linux = _job("linux", BUILD)
    assert "runs-on: ubuntu-latest" in linux and "name: maily-linux-x64" in linux
    assert "xvfb-run -a dist/Maily/maily --self-check --window" in linux
    assert linux.index("--self-check") < linux.index("tar -C dist")
    for f in ("maily.desktop", "INSTALL.txt", "maily.png"):
        assert f in linux
    smoke = _job("linux-smoke", BUILD)
    assert "needs: linux" in smoke and "--self-check --window" in smoke


def test_every_build_is_uploaded_with_its_checksum():
    assert BUILD.count("actions/upload-artifact@") == 3
    assert BUILD.count("if-no-files-found: error") == 3
    assert BUILD.count(".sha256") >= 3


def test_publish_creates_a_draft_with_the_files_then_publishes_it():
    publish = _job("publish")
    assert "actions/download-artifact@" in publish
    assert "pattern: maily-*" in publish and "merge-multiple: true" in publish
    assert "scripts/release_notes.py assets" in publish
    assert "Missing build file" in publish
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
