# Building a standalone application

You do not need to build anything to use Maily: `uv run maily` runs it from the source folder (`uv run python -m app.bootstrap` does the same). This page is for people who want a double-clickable application (`Maily.app` on macOS, an executable folder on Linux and Windows).

## Downloading the macOS app

Every [release](https://github.com/ThanaelFontaine/Maily/releases) comes with a ready-made app for Macs with Apple Silicon, built by the CI from the tagged code:

- `Maily-X.Y.Z-macos-arm64.zip`: the zipped `Maily.app`;
- `Maily-X.Y.Z-macos-arm64.zip.sha256`: its SHA-256 checksum.

Check the download, then unzip it and move `Maily.app` to your Applications folder:

```bash
shasum -a 256 -c Maily-X.Y.Z-macos-arm64.zip.sha256    # prints "Maily-X.Y.Z-macos-arm64.zip: OK"
```

**The app is not signed with an Apple Developer ID and not notarized.** The first time you open it, macOS shows a warning and refuses to open it, because it cannot check the app. To open it anyway ([Apple's instructions](https://support.apple.com/guide/mac-help/open-a-mac-app-from-an-unknown-developer-mh40616/mac)):

1. Try to open `Maily.app` once, and close the warning.
2. Choose Apple menu > *System Settings*, then click *Privacy & Security* in the sidebar.
3. Go to *Security*, then click *Open Anyway* next to the message about Maily. Apple notes that the button is available for about an hour after you try to open the app.
4. Enter your login password, then click *OK*. Maily opens, and macOS keeps it as an exception from then on.

From a terminal, you can instead remove the quarantine flag that macOS puts on downloaded files: `xattr -dr com.apple.quarantine /Applications/Maily.app`. Only do this for a file whose checksum you checked.

The downloaded app uses the same data folder as the source version (see [Where your data lives](../README.md#where-your-data-lives)), so both share accounts and mail. To update it, download the new zip from the latest release and replace `Maily.app`. If you prefer not to run an unsigned binary, run Maily from source or build it yourself as explained below.

## How the app is packaged

Maily is packaged with **PyInstaller** (spec: [`packaging/maily.spec`](../packaging/maily.spec), entry point: [`run_maily.py`](../run_maily.py)). The `frontend/` and `migrations/` folders are embedded; paths are "frozen-aware" (`sys._MEIPASS`). The version shown in the app bundle is read from `core/__init__.py`.

> **No cross-compilation.** Each platform builds on itself: a macOS binary on a Mac, a Windows binary on Windows, a Linux binary on Linux.

A self-built app also uses the same data folder as the source version. The MCP server is not part of the packaged app: it always runs from a source folder (see [docs/MCP.md](MCP.md)).

## Common prerequisite

```bash
uv sync --group build      # dependencies + PyInstaller + Pillow
```

## macOS (Apple Silicon)

```bash
uv run pyinstaller packaging/maily.spec --noconfirm
# -> dist/Maily.app
open dist/Maily.app
```

The helper script `scripts/build_macos.sh` does the same, regenerates the icon if needed, and **replaces `/Applications/Maily.app`** with the new build (then removes `dist/Maily.app` so that Spotlight shows a single Maily). Read it before running it.

To share the bundle the way the CI does (`ditto` keeps the bundle's symbolic links and metadata, unlike a plain `zip`):

```bash
ditto -c -k --sequesterRsrc --keepParent dist/Maily.app Maily-X.Y.Z-macos-arm64.zip
shasum -a 256 Maily-X.Y.Z-macos-arm64.zip > Maily-X.Y.Z-macos-arm64.zip.sha256
```

The bundle is **neither signed nor notarized**: see [Downloading the macOS app](#downloading-the-macos-app) for how to open it. For wide distribution, sign it with an Apple Developer certificate and notarize it (`codesign`, `notarytool`).

Touch ID works in the packaged app (framework `LocalAuthentication`, embedded).

## Linux (x86_64)

pywebview needs **GTK and WebKit2GTK** (Debian/Ubuntu package names):

```bash
sudo apt-get update
sudo apt-get install -y \
  libgtk-3-0 gir1.2-gtk-3.0 gir1.2-webkit2-4.1 libwebkit2gtk-4.1-0 \
  libgirepository1.0-dev libcairo2-dev pkg-config python3-dev
uv sync --group build
uv pip install pygobject          # GTK bindings
uv run pyinstaller packaging/maily.spec --noconfirm
# -> dist/Maily/   (run: ./dist/Maily/Maily)
cd dist && tar czf ../Maily-linux-x64.tar.gz Maily
```

Recent Ubuntu releases may need a specific PyGObject version matching their `girepository`; if `pygobject` fails to build, try `uv pip install "pygobject==3.50.0"`. Without GTK, you can install `pyside6` and run with `PYWEBVIEW_GUI=qt`.

The same system packages are needed to run from source on Linux (`uv pip install pygobject`, then `uv run maily`).

## Windows (x86_64)

pywebview uses **WebView2 (Edge Chromium)**, present on up-to-date Windows 10 and 11.

```powershell
uv sync --group build
uv run pyinstaller packaging/maily.spec --noconfirm
# -> dist\Maily\   (run: dist\Maily\Maily.exe)
Compress-Archive -Path dist\Maily -DestinationPath Maily-windows-x64.zip
```

## Checking TLS in a built app

The packaged binary embeds the `certifi` CA bundle. To check it:

```bash
dist/Maily.app/Contents/MacOS/Maily --tls-selftest     # macOS
./dist/Maily/Maily --tls-selftest                      # Linux
```

It should print `TLS OK`.

## Releases

Releases are created by the CI, not by hand: after the tests pass on a push to `main`, `.github/workflows/release.yml` reads the version in `pyproject.toml`, and if the tag `vX.Y.Z` does not exist yet, creates it with a GitHub release whose notes are the matching section of `CHANGELOG.md`. See [CONTRIBUTING.md](../CONTRIBUTING.md#releasing-a-version).

The same workflow then runs a `macos-app` job on a GitHub-hosted macOS runner (`macos-latest`, Apple Silicon): `uv sync --locked --group build`, `pyinstaller packaging/maily.spec`, a check that the bundle version matches the tag, the `ditto` zip and its checksum above, and `gh release upload vX.Y.Z Maily-X.Y.Z-macos-arm64.zip Maily-X.Y.Z-macos-arm64.zip.sha256 --clobber`. It lives in the release workflow because a tag or a release created with the workflow's `GITHUB_TOKEN` does not start other workflows. `--clobber` replaces assets that already have the same name, so a new upload never leaves two copies.

Linux and Windows binaries are not built by the CI yet; built on their platform as above, they can be attached to the release by a maintainer:

```bash
gh release upload vX.Y.Z Maily-linux-x64.tar.gz    # from Linux
gh release upload vX.Y.Z Maily-windows-x64.zip     # from Windows
```
