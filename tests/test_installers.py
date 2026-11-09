"""install.sh (macOS and Linux) and install.ps1 (Windows): the build attestation
is checked with the GitHub CLI before anything is installed.

install.sh runs for real, on Linux x64 as far as it can tell, inside a PATH
that holds only the tools it needs plus a fake `curl` (serves local files), a
fake `uname` and a fake `gh` (records its calls, answers as the test says).
install.ps1 cannot run here: it is checked as text.
"""
import hashlib
import os
import pathlib
import shutil
import stat
import subprocess
import sys
import tarfile

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
INSTALL_SH = ROOT / "packaging" / "install" / "install.sh"
INSTALL_PS1 = ROOT / "packaging" / "install" / "install.ps1"
SIGNER = "ThanaelFontaine/Maily/.github/workflows/release.yml"

# Everything install.sh calls on the Linux path, taken from the real system.
TOOLS = ["sh", "tar", "awk", "cut", "tr", "mktemp", "rm", "mkdir", "mv", "ln", "cp", "sed", "grep", "cat", "dirname", "basename", "gzip"]

FAKE_CURL = f"""#!{sys.executable}
import os, shutil, sys
args = sys.argv[1:]
url = [a for a in args if a.startswith("http")][-1]
out = None
for i, a in enumerate(args):
    if a == "-o":
        out = args[i + 1]
if url.endswith("/releases/latest"):
    print(f"https://github.com/ThanaelFontaine/Maily/releases/tag/v{{os.environ['FAKE_LATEST']}}", end="")
    sys.exit(0)
src = os.path.join(os.environ["FAKE_SERVER"], url.rsplit("/", 1)[1])
if not os.path.exists(src):
    sys.exit(22)
shutil.copyfile(src, out)
"""

FAKE_UNAME = """#!/bin/sh
case "$1" in
  -s) echo Linux ;;
  -m) echo x86_64 ;;
  *) echo Linux ;;
esac
"""

FAKE_PGREP = "#!/bin/sh\nexit 1\n"

# FAKE_GH_MODE: ok (signed in, attestation valid), invalid (verification fails),
# unauth (not signed in), old (no `attestation` command).
FAKE_GH = """#!/bin/sh
echo "$*" >> "$FAKE_GH_LOG"
case "$1 $2" in
  "attestation verify")
    [ "$FAKE_GH_MODE" = "old" ] && exit 1
    [ "$3" = "--help" ] && exit 0
    [ "$FAKE_GH_MODE" = "invalid" ] && { echo "Error: verification failed" >&2; exit 1; }
    echo "Loaded digest"; exit 0 ;;
  "auth status")
    [ "$FAKE_GH_MODE" = "unauth" ] && exit 1
    exit 0 ;;
esac
exit 0
"""


def _exe(path: pathlib.Path, text: str):
    path.write_text(text)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def env(tmp_path):
    """A release server directory, a controlled PATH and a way to run install.sh."""
    server = tmp_path / "server"
    server.mkdir()
    bindir = tmp_path / "bin"
    bindir.mkdir()
    for tool in TOOLS:
        found = shutil.which(tool)
        assert found, tool
        (bindir / tool).symlink_to(found)
    # sha256sum on Linux, shasum on macOS: install.sh takes whichever exists.
    for tool in ("sha256sum", "shasum"):
        found = shutil.which(tool)
        if found:
            (bindir / tool).symlink_to(found)
    _exe(bindir / "curl", FAKE_CURL)
    _exe(bindir / "uname", FAKE_UNAME)
    _exe(bindir / "pgrep", FAKE_PGREP)
    ghdir = tmp_path / "ghbin"
    ghdir.mkdir()
    _exe(ghdir / "gh", FAKE_GH)
    home = tmp_path / "home"
    home.mkdir()
    install_dir = tmp_path / "opt"
    gh_log = tmp_path / "gh.log"

    def publish(version: str, *, corrupt: bool = False):
        """The Linux archive of `version` and its .sha256, as the CI makes them."""
        app = tmp_path / "stage" / "Maily"
        app.mkdir(parents=True, exist_ok=True)
        _exe(app / "maily", "#!/bin/sh\necho maily\n")
        (app / "maily.png").write_bytes(b"png")
        (app / "maily.desktop").write_text("[Desktop Entry]\nExec=maily\n")
        name = f"Maily-{version}-linux-x64.tar.gz"
        with tarfile.open(server / name, "w:gz") as tar:
            tar.add(app, arcname="Maily")
        digest = _sha(server / name)
        if corrupt:
            digest = "0" * 64
        (server / f"{name}.sha256").write_text(f"{digest}  {name}\n")

    def run(version=None, *, gh=None, require=False):
        path = str(bindir)
        if gh is not None:
            path = f"{ghdir}{os.pathsep}{path}"
        e = {
            "PATH": path,
            "HOME": str(home),
            "FAKE_SERVER": str(server),
            "FAKE_LATEST": "0.10.0",
            "FAKE_GH_LOG": str(gh_log),
            "FAKE_GH_MODE": gh or "ok",
            "MAILY_INSTALL_DIR": str(install_dir),
        }
        if version:
            e["MAILY_VERSION"] = version
        if require:
            e["MAILY_REQUIRE_ATTESTATION"] = "1"
        return subprocess.run([shutil.which("sh"), str(INSTALL_SH)], env=e, capture_output=True, text=True, timeout=60)

    class Env:
        pass

    o = Env()
    o.publish, o.run, o.install_dir, o.gh_log = publish, run, install_dir, gh_log
    o.installed = lambda: (install_dir / "Maily" / "maily").exists()
    o.gh_calls = lambda: gh_log.read_text().splitlines() if gh_log.exists() else []
    return o


def test_installer_files_are_valid_shell():
    subprocess.run([shutil.which("sh"), "-n", str(INSTALL_SH)], check=True)


def test_valid_attestation_installs_and_checks_the_right_file(env):
    env.publish("0.10.0")
    r = env.run(gh="ok")
    assert r.returncode == 0, r.stderr + r.stdout
    assert "Checksum verified." in r.stdout and "Attestation verified" in r.stdout
    assert env.installed()
    verify = [c for c in env.gh_calls() if c.startswith("attestation verify") and "--help" not in c]
    assert len(verify) == 1
    assert verify[0].endswith(
        f"--repo ThanaelFontaine/Maily --signer-workflow {SIGNER} "
        "--source-ref refs/heads/main --deny-self-hosted-runners")


def test_invalid_attestation_stops_before_installing(env):
    env.publish("0.10.0")
    r = env.run(gh="invalid")
    assert r.returncode != 0
    assert "could not be verified. Nothing was installed." in r.stderr
    assert not env.installed()


def test_invalid_attestation_stops_even_when_not_required(env):
    env.publish("0.10.0")
    assert env.run(gh="invalid", require=False).returncode != 0


def test_without_gh_the_install_goes_on_with_a_warning(env):
    env.publish("0.10.0")
    r = env.run(gh=None)
    assert r.returncode == 0, r.stderr
    assert "Warning: could not check where this download was built" in r.stdout
    assert "SECURITY.md#verify-a-download" in r.stdout
    assert env.installed()


def test_without_gh_and_attestation_required_nothing_is_installed(env):
    env.publish("0.10.0")
    r = env.run(gh=None, require=True)
    assert r.returncode != 0
    assert "MAILY_REQUIRE_ATTESTATION=1" in r.stderr
    assert not env.installed()


def test_gh_not_signed_in_warns_and_goes_on(env):
    env.publish("0.10.0")
    r = env.run(gh="unauth")
    assert r.returncode == 0, r.stderr
    assert "gh auth login" in r.stdout
    assert env.installed()
    assert not [c for c in env.gh_calls() if c.startswith("attestation verify") and "--help" not in c]


def test_gh_not_signed_in_and_attestation_required_fails(env):
    env.publish("0.10.0")
    r = env.run(gh="unauth", require=True)
    assert r.returncode != 0 and not env.installed()


def test_an_old_gh_without_attestation_is_a_warning_not_a_failure(env):
    env.publish("0.10.0")
    r = env.run(gh="old")
    assert r.returncode == 0, r.stderr
    assert "update it" in r.stdout and env.installed()


def test_a_release_older_than_0_10_0_installs_with_a_warning_and_never_calls_gh(env):
    env.publish("0.9.2")
    r = env.run("0.9.2", gh="ok")
    assert r.returncode == 0, r.stderr
    assert "older than 0.10.0" in r.stdout
    assert env.installed()
    assert not [c for c in env.gh_calls() if c.startswith("attestation verify")]


def test_an_old_release_with_attestation_required_is_refused(env):
    env.publish("0.9.2")
    r = env.run("0.9.2", gh="ok", require=True)
    assert r.returncode != 0 and not env.installed()


def test_a_bad_checksum_stops_before_the_attestation(env):
    env.publish("0.10.0", corrupt=True)
    r = env.run(gh="ok")
    assert r.returncode != 0
    assert "does not match its SHA-256 checksum" in r.stderr
    assert not env.installed()
    assert not env.gh_calls()


def test_the_latest_version_is_found_from_the_github_redirect(env):
    env.publish("0.10.0")
    r = env.run(gh="ok")
    assert "Downloading Maily 0.10.0 for Linux" in r.stdout


@pytest.mark.parametrize("path", [INSTALL_SH, INSTALL_PS1])
def test_both_installers_pin_the_signer_and_the_repository(path):
    text = path.read_text(encoding="utf-8")
    assert "ThanaelFontaine/Maily" in text and ".github/workflows/release.yml" in text
    assert "--signer-workflow" in text and "--repo" in text
    assert "refs/heads/main" in text and "--deny-self-hosted-runners" in text
    assert "MAILY_REQUIRE_ATTESTATION" in text
    assert "0.10.0" in text
    assert "releases/latest/download/install" in text


@pytest.mark.parametrize("path", [INSTALL_SH, INSTALL_PS1])
def test_installers_point_at_the_github_release_not_the_site(path):
    text = path.read_text(encoding="utf-8")
    assert "maily.thanaelfontaine.eu/install" not in text
    # No dash characters other than the plain hyphen (writing rule).
    assert chr(0x2014) not in text and chr(0x2013) not in text


def test_powershell_installer_checks_before_extracting():
    text = INSTALL_PS1.read_text(encoding="utf-8")
    assert text.index("Checking the build attestation") < text.index("Expand-Archive")
    assert text.index("Get-FileHash") < text.index("Checking the build attestation")
    assert "Nothing was installed." in text


def _version_tuple(v):
    return tuple(int(p) for p in v.split("."))


def test_readme_install_commands_use_the_installers_of_the_latest_release():
    # The one-line commands must serve the installers attached to the release
    # (with their attestation), never the copies on main (MAIL-34 lot 6).
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    base = "https://github.com/ThanaelFontaine/Maily/releases/latest/download/"
    assert f"curl -fsSL {base}install.sh | sh" in text
    assert f"irm {base}install.ps1 | iex" in text
    assert "raw.githubusercontent.com/ThanaelFontaine/Maily/main/packaging/install" not in text


@pytest.mark.parametrize("path", [INSTALL_SH, INSTALL_PS1])
def test_installer_header_example_version_is_a_real_version(path):
    # The "MAILY_VERSION = x.y.z installs that version" example must not name a
    # version that does not exist yet, nor fall behind more than the project's
    # own version allows (it was left on 0.9.2 after 0.10.0).
    import re
    text = path.read_text(encoding="utf-8")
    m = re.search(r'MAILY_VERSION\s*=\s*"?(\d+\.\d+\.\d+)', text)
    assert m, "the header must give an example version"
    project = re.search(r'^version = "(\d+\.\d+\.\d+)"', (ROOT / "pyproject.toml").read_text(encoding="utf-8"), re.M).group(1)
    assert _version_tuple(m.group(1)) <= _version_tuple(project)
    assert _version_tuple(m.group(1)) >= (0, 10, 0)


def test_lockfile_keeps_oauthlib_past_the_advisory():
    # Dependabot alert 69: oauthlib >= 3.3.0 and < 4.0.1 is vulnerable.
    import tomllib
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    versions = [p["version"] for p in lock["package"] if p["name"] == "oauthlib"]
    assert versions, "oauthlib is no longer locked: re-check alert 69"
    assert all(_version_tuple(v) >= (4, 0, 1) for v in versions)
