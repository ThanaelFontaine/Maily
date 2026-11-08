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


def test_assets_are_the_three_builds_the_installers_and_their_checksums():
    assets = _rn().assets("1.2.3")
    assert assets == [
        "Maily-1.2.3-macos-arm64.dmg", "Maily-1.2.3-macos-arm64.dmg.sha256",
        "Maily-1.2.3-windows-x64.zip", "Maily-1.2.3-windows-x64.zip.sha256",
        "Maily-1.2.3-linux-x64.tar.gz", "Maily-1.2.3-linux-x64.tar.gz.sha256",
        "Maily-macos-arm64.dmg", "Maily-windows-x64.zip", "Maily-linux-x64.tar.gz",
        "install.sh", "install.sh.sha256", "install.ps1", "install.ps1.sha256",
    ]
    assert len(assets) == 13 and len(set(assets)) == 13


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
    assert "ref: ${{ github.event.workflow_run.head_sha || github.sha }}" in build
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
    # Pinned: PyGObject is compiled against the girepository of the build
    # machine, so ubuntu-latest (26.04) made the archive fail on Debian 13.
    assert "runs-on: ubuntu-24.04" in linux and "name: maily-linux-x64" in linux
    assert "xvfb-run -a dist/Maily/maily --self-check --window" in linux
    assert linux.index("--self-check") < linux.index("tar -C dist")
    for f in ("maily.desktop", "INSTALL.txt", "maily.png"):
        assert f in linux
    smoke = _job("linux-smoke", BUILD)
    assert "needs: linux" in smoke and "--self-check --window" in smoke
    for image in ("ubuntu:24.04", "debian:trixie", "fedora:latest"):
        assert f"image: {image}" in smoke
    assert smoke.index("--self-check --window") < smoke.index("./Maily/maily --tls-selftest")


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
    assert '-ge 13' in publish and '-ge 9' not in publish
    create = publish.rindex("gh release create")
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


# ---- Provenance (MA-5, MAIL-20): attestations, installers, dry run -----------

def test_only_the_publish_job_can_write_and_attest():
    publish = _job("publish")
    for perm in ("contents: write", "id-token: write", "attestations: write"):
        assert perm in publish
    for name in ("plan", "build"):
        job = _job(name)
        for perm in ("id-token: write", "attestations: write", "contents: write"):
            assert perm not in job
    # the workflow-level default stays read-only, and build.yml is not elevated
    top = WORKFLOW.split("\njobs:\n")[0]
    assert "permissions:\n  contents: read" in top
    assert "id-token" not in BUILD and "attestations" not in BUILD


def test_every_action_is_pinned_by_full_sha():
    for text in (WORKFLOW, BUILD):
        for line in re.findall(r"^\s+- uses: (\S+)|^\s+uses: (\S+)", text, re.M):
            ref = "".join(line)
            if ref.startswith("./"):
                continue
            assert re.fullmatch(r".+@[0-9a-f]{40}", ref), ref


def test_the_release_files_are_attested_before_the_draft_is_created():
    publish = _job("publish")
    m = re.search(r"uses: actions/attest@([0-9a-f]{40}) # v\d+\.\d+\.\d+\n\s+with:\n\s+subject-path: release-assets/\*", publish)
    assert m, "actions/attest pinned by SHA with subject-path release-assets/*"
    assert publish.index("actions/attest@") < publish.index("gh release create")
    # the attested files are final: the installers and aliases are added before
    assert publish.index("packaging/install/") < publish.index("actions/attest@")
    assert publish.index("release_notes.py aliases") < publish.index("actions/attest@")


def test_the_installers_come_from_the_tested_commit_with_their_checksums():
    publish = _job("publish")
    assert 'cp "packaging/install/$f" "release-assets/$f"' in publish
    assert "for f in install.sh install.ps1" in publish
    assert '"$f.sha256"' in publish
    assert (ROOT / "packaging" / "install" / "install.sh").is_file()
    assert (ROOT / "packaging" / "install" / "install.ps1").is_file()


def test_a_published_release_is_never_completed_or_modified():
    assert "gh release upload" not in WORKFLOW
    publish = _job("publish")
    assert "already published" in publish
    plan = _job("plan")
    assert "A published release is final" in plan
    assert "needed=false" in plan


def _dry_run_block():
    publish = _job("publish")
    start = publish.index('if [ "$DRY_RUN" = "true" ]; then')
    end = publish.index("exit 0\n          fi", start)
    return publish[start:end]


def test_dry_run_is_a_manual_trigger_that_defaults_to_true():
    assert re.search(r"workflow_dispatch:\n    inputs:\n      dry_run:\n(?:        .*\n)*?        type: boolean\n        default: true", WORKFLOW)
    plan = _job("plan")
    # a manual run that is not a dry run is refused
    assert '"$DISPATCH" = "true" ] && [ "$DRY_RUN" != "true"' in plan
    assert "exit 1" in plan[plan.index('"$DISPATCH" = "true" ] && [ "$DRY_RUN" != "true"'):][:400]
    # a push to main is still published, only by the Tests workflow
    assert "workflow_run.conclusion == 'success'" in plan


def test_dry_run_publishes_nothing_and_removes_its_draft():
    block = _dry_run_block()
    for forbidden in ("git push", "git tag", "--draft=false", "--verify-tag", "announce=true", "gh release edit"):
        assert forbidden not in block
    assert "--draft --target" in block
    assert "trap " in block and "-X DELETE" in block and " EXIT" in block
    assert "gh attestation verify" in block and "--signer-workflow" in block
    assert "cmp " in block  # the downloaded copy is the built file
    # the drafts of a dry run have a name that no real tag can have
    assert 'dry-run-$GITHUB_RUN_ID' in block


def test_dry_run_runs_even_when_the_version_is_already_published():
    plan = _job("plan")
    i = plan.index('if [ "$DISPATCH" = "true" ]; then')
    assert "needed=true" in plan[i:i + 300]
    # and it comes before the published-release check
    assert i < plan.index("gh release view")


def test_the_discord_announcement_only_follows_a_real_publication():
    publish = _job("publish")
    assert "steps.publish.outputs.announce == 'true'" in publish
    assert publish.count("announce=true") == 1
    assert publish.index("announce=true") > publish.index("gh release edit")


def test_the_publish_job_stays_on_a_github_machine():
    assert "runs-on: ubuntu-latest" in _job("publish")
    for text in (WORKFLOW, BUILD):
        assert not [l for l in re.findall(r"^\s+runs-on:.*$", text, re.M) if "self-hosted" in l]
